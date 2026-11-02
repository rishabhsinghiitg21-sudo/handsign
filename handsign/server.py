"""Local web server bridging the handsign engine to the tactical console.

Runs HandsFreeEngine headless in a worker thread and exposes:

  REST
    GET  /api/status                      engine + system state
    GET  /api/config    PUT /api/config   read / write gestures.json
    GET  /api/dataset                     recorded labels + sample counts
    GET  /api/dataset/{label}/samples     landmark arrays (dummy-hand preview)
    POST /api/calibrate/classifier        offline LOO calibration report
    POST /api/engine/start  /stop         control the headless engine
  WS
    /ws/live                              ~20 Hz telemetry: pose, confidence,
                                          hold, mode, mic, sequence progress,
                                          21-pt hands, fire events, opt. frame

Only one process can own the webcam, so while the engine runs here the CLI
`run` must be stopped (and vice-versa). Static frontend (Vite build) is served
from web/dist if present.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import threading
import time
from collections import deque
from pathlib import Path

# Let OpenCV use the camera permission we request explicitly via AVFoundation;
# its own auth request can't run from the engine's worker thread. Must be set
# before cv2 is imported.
os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from fastapi.staticfiles import StaticFiles

from .classifier import PoseClassifier
from .config import Config
from .engine import HandsFreeEngine
from .face import EXPRESSION_NAMES
from .fsutil import atomic_write_text
from .gestures_builtin import BUILTIN_GESTURES
from .recognizer import Recognizer
from .record_session import RecordSession
from .speech import Transcriber
from .voice import VoiceRouter

log = logging.getLogger("uvicorn.error")

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "gestures.json"
DATASET_PATH = ROOT / "data" / "dataset.json"
WEB_DIST = ROOT / "web" / "dist"


# --------------------------------------------------------------- local-only
# SECURITY. Bindings can run shell commands (see actions.py) and PUT /api/config
# can write them, so a web page open in the user's browser must never be able to
# talk to this server. Defence in depth:
#   1. the server binds to loopback only (see serve());
#   2. CORS is limited to the console's own origins;
#   3. any HTTP or WebSocket request that carries an Origin header outside that
#      list is refused (403), and the Host header must be a loopback name, which
#      also stops DNS-rebinding;
#   4. every WebSocket handler re-checks the Origin before it accepts.
# Requests with no Origin header (curl, scripts, same-origin GETs) are allowed:
# anything running on this machine as you could run shell commands anyway.
DEFAULT_PORT = 8000
VITE_DEV_PORT = 5173
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
ALLOWED_ORIGINS: list[str] = []   # mutated in place by configure_origins()


def configure_origins(port: int = DEFAULT_PORT) -> None:
    """Allow the console's own origins: this server's port and the Vite dev port."""
    ALLOWED_ORIGINS[:] = [
        f"http://{host}:{p}"
        for p in (port, VITE_DEV_PORT)
        for host in ("127.0.0.1", "localhost")
    ]


configure_origins()


def _hostname(host_header: str) -> str:
    """'localhost:8000' -> 'localhost'; '[::1]:8000' -> '::1'."""
    h = host_header.strip().lower()
    if h.startswith("["):
        return h[1:].split("]", 1)[0]
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


def request_allowed(headers: dict[str, str]) -> bool:
    """True if the Origin (when present) and Host headers are local."""
    origin = headers.get("origin")
    if origin is not None and origin not in ALLOWED_ORIGINS:
        return False
    host = headers.get("host")
    if host is not None and _hostname(host) not in LOOPBACK_HOSTS:
        return False
    return True


def _header_dict(scope: Scope) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])}


class LocalOnlyMiddleware:
    """Pure-ASGI so it covers WebSocket handshakes as well as HTTP."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket") and not request_allowed(_header_dict(scope)):
            if scope["type"] == "http":
                resp = JSONResponse(
                    {"detail": "forbidden: handsign only accepts requests from its own "
                               "console on localhost"}, status_code=403)
                await resp(scope, receive, send)
            else:
                await receive()  # the websocket.connect event
                await send({"type": "websocket.close", "code": 1008})
            return
        await self.app(scope, receive, send)


async def accept_local(ws: WebSocket) -> bool:
    """Accept a WebSocket only from a local, allow-listed origin."""
    if not request_allowed({k.lower(): v for k, v in ws.headers.items()}):
        await ws.close(code=1008)
        return False
    await ws.accept()
    return True


class EngineManager:
    """Owns the engine thread and the shared telemetry the WS loop reads."""

    def __init__(self):
        self._engine: HandsFreeEngine | None = None
        self._record: RecordSession | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest: dict = {}                 # most recent frame telemetry
        self._events: deque = deque(maxlen=200)  # fire events (drained by WS)
        self.flags: dict = {}
        self.mode: str = "idle"                 # idle | run | record
        self.live: bool = False                 # browser camera stream active
        self.live_flags: dict = {}
        self.voice_live: bool = False            # browser mic stream active
        self.last_pose: str | None = None        # for combined gesture+voice bindings
        self.last_expression: str | None = None
        self._transcriber: Transcriber | None = None
        self._tx_lock = threading.Lock()
        self._ctl = threading.RLock()           # serialises start / stop (REST runs in a thread pool)

    def get_transcriber(self) -> Transcriber:
        """Lazily load and cache the speech model (shared across voice sockets)."""
        with self._tx_lock:
            if self._transcriber is None:
                cfg = Config.load(CONFIG_PATH)
                self._transcriber = Transcriber(
                    model=cfg.voice("model"),
                    device=cfg.voice("device"),
                    compute_type=cfg.voice("compute_type"),
                )
            return self._transcriber

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _sink(self, payload: dict) -> None:
        if payload.get("type") == "frame":
            with self._lock:
                self._latest = payload
        else:
            payload["t"] = time.time()
            self._events.append(payload)

    def start(self, dry_run: bool, voice: bool, mouse: bool) -> None:
        with self._ctl:
            self._start(dry_run, voice, mouse)

    def _start(self, dry_run: bool, voice: bool, mouse: bool) -> None:
        if self.running:
            raise RuntimeError("engine already running")
        self._events.clear()
        self._latest = {}
        self.flags = {"dry_run": dry_run, "voice": voice, "mouse": mouse}
        engine = HandsFreeEngine(
            CONFIG_PATH, DATASET_PATH,
            dry_run=dry_run, show=False,
            enable_voice=voice, enable_mouse=mouse,
            event_sink=self._sink,
        )
        self._engine = engine
        self.mode = "run"
        self._thread = threading.Thread(target=self._run_safe, daemon=True)
        self._thread.start()

    def start_record(self) -> None:
        with self._ctl:
            self._start_record()

    def _start_record(self) -> None:
        if self.running:
            raise RuntimeError("stop the current session before recording")
        self._events.clear()
        self._latest = {}
        cfg = Config.load(CONFIG_PATH)
        self._record = RecordSession(
            DATASET_PATH, int(cfg.setting("camera_index")), self._sink
        )
        self.mode = "record"
        self._thread = threading.Thread(target=self._run_record_safe, daemon=True)
        self._thread.start()

    def capture(self, label: str) -> dict:
        if self._record is None:
            raise RuntimeError("not in record mode")
        self._record.capture(label)
        return self._record.counts()

    def save_record(self) -> dict:
        if self._record is None:
            raise RuntimeError("not in record mode")
        return self._record.save()

    def _run_safe(self) -> None:
        try:
            self._engine.run()
        except Exception as e:  # surface as an event rather than dying silently
            self._events.append({"type": "event", "kind": "error",
                                 "name": str(e), "t": time.time()})

    def _run_record_safe(self) -> None:
        try:
            self._record.run()
        except Exception as e:
            self._events.append({"type": "event", "kind": "error",
                                 "name": str(e), "t": time.time()})

    def stop(self) -> None:
        with self._ctl:
            self._stop()

    def _stop(self) -> None:
        if self._engine is not None:
            self._engine.stop()
        if self._record is not None:
            self._record.stop()
        if self._thread is not None:
            self._thread.join(timeout=4.0)
        self._engine = None
        self._record = None
        self._thread = None
        self._latest = {}
        self.mode = "idle"

    def snapshot(self) -> tuple[dict, list]:
        with self._lock:
            latest = dict(self._latest)
        events = []
        while self._events:
            events.append(self._events.popleft())
        return latest, events


manager = EngineManager()
app = FastAPI(title="handsign console")
app.add_middleware(
    CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type"],
)
app.add_middleware(LocalOnlyMiddleware)   # added last = outermost: runs first


# ----------------------------------------------------------------- REST
@app.get("/api/status")
def status():
    cfg = Config.load(CONFIG_PATH)
    clf = PoseClassifier.load(DATASET_PATH)
    return {
        "engine_running": manager.running,
        "live": manager.live,
        "voice_live": manager.voice_live,
        "live_flags": manager.live_flags,
        "mode": manager.mode,
        "flags": manager.flags,
        "model_present": all((ROOT / "data" / f"{m}.task").exists()
                             for m in ("hand_landmarker", "face_landmarker")),
        "gestures": clf.labels,
        "gesture_names": sorted(set(clf.labels) | set(BUILTIN_GESTURES)),
        "builtin_gestures": BUILTIN_GESTURES,
        "sample_counts": clf.counts(),
        "poses": list(cfg.poses),
        "sequences": [s.name for s in cfg.sequences],
        "voice_commands": list(cfg.voice_commands),
        "expressions": list(cfg.expressions),
        "expression_names": EXPRESSION_NAMES,
        "workflows": {n: len(steps) for n, steps in cfg.workflows.items()},
        "push_to_talk": cfg.push_to_talk,
        "mouse_gesture": cfg.mouse("gesture"),
    }


@app.post("/api/workflow/{name}/trigger")
def workflow_trigger(name: str):
    """Run a workflow now (real dispatch — needs Accessibility permission)."""
    from .workflows import start_workflow
    cfg = Config.load(CONFIG_PATH)
    steps = cfg.workflows.get(name)
    if steps is None:
        raise HTTPException(404, f"no workflow '{name}'")
    start_workflow(steps)
    return {"ok": True, "ran": name, "steps": len(steps)}


@app.get("/api/config")
def get_config():
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text())


@app.put("/api/config")
async def put_config(payload: dict):
    # Validate by parsing it the way the engine will, then replace the file
    # atomically so a crash mid-write can never leave a broken gestures.json.
    try:
        Config.from_dict(payload)
    except Exception as e:
        raise HTTPException(400, f"invalid config: {type(e).__name__}: {e}")
    atomic_write_text(CONFIG_PATH, json.dumps(payload, indent=2))
    return {"ok": True}


@app.get("/api/dataset")
def get_dataset():
    clf = PoseClassifier.load(DATASET_PATH)
    return {"labels": clf.labels, "counts": clf.counts()}


@app.get("/api/dataset/{label}/samples")
def get_samples(label: str, limit: int = 12):
    """Return landmark arrays for a label + the medoid (for dummy-hand preview)."""
    clf = PoseClassifier.load(DATASET_PATH)
    V, labels = clf.vectors, clf.label_list
    idx = [i for i, l in enumerate(labels) if l == label]
    if not idx:
        # Built-in poses have no recordings; answer 200/empty so the UI can show
        # "no preview" without a failed request in the console.
        return {"label": label, "feature_dim": 0, "medoid": None, "samples": [], "count": 0}
    sub = V[idx]  # (n, 63) features (already normalized 21x3 flattened)
    # medoid = sample with min total distance to others
    d = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2).sum(axis=1)
    medoid = sub[int(np.argmin(d))]
    take = sub[:limit]
    return {
        "label": label,
        "feature_dim": sub.shape[1],
        "medoid": medoid.reshape(21, 3).tolist(),
        "samples": [s.reshape(21, 3).tolist() for s in take],
        "count": len(idx),
    }


@app.post("/api/calibrate/classifier")
def calibrate_classifier():
    from . import calibrate as cal
    sug, report = cal.calibrate_classifier(DATASET_PATH)
    return {"suggestions": sug, "report": report}


@app.post("/api/calibrate/{target}")
def calibrate_other(target: str):
    raise HTTPException(
        501, f"'{target}' calibration is interactive (camera/mic) — run "
             f"`./handsign.sh calibrate {target}` in a terminal.")


@app.post("/api/engine/start")
def engine_start(payload: dict | None = None):
    payload = payload or {}
    try:
        manager.start(
            dry_run=bool(payload.get("dry_run", True)),
            voice=bool(payload.get("voice", True)),
            mouse=bool(payload.get("mouse", True)),
        )
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    return {"ok": True, "flags": manager.flags}


@app.post("/api/engine/stop")
def engine_stop():
    manager.stop()
    return {"ok": True}


# ---- record (browser-driven gesture capture) ----
@app.post("/api/record/start")
def record_start():
    try:
        manager.start_record()
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    return {"ok": True, "mode": manager.mode}


@app.post("/api/record/capture")
def record_capture(payload: dict):
    label = (payload or {}).get("label", "").strip()
    if not label:
        raise HTTPException(400, "label required")
    try:
        counts = manager.capture(label)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "counts": counts}


@app.post("/api/record/save")
def record_save():
    try:
        counts = manager.save_record()
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "counts": counts}


@app.delete("/api/dataset/{label}")
def delete_label(label: str):
    clf = PoseClassifier.load(DATASET_PATH)
    n = clf.remove_label(label)
    clf.save(DATASET_PATH)
    return {"ok": True, "removed": n}


# ----------------------------------------------------------------- WebSocket
def _encode_frame(frame_bgr: np.ndarray, width: int = 480, quality: int = 60) -> str:
    h, w = frame_bgr.shape[:2]
    if w > width:
        frame_bgr = cv2.resize(frame_bgr, (width, int(h * width / w)))
    ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf).decode() if ok else ""


async def _send_error(ws: WebSocket, message: str) -> None:
    """Best-effort: tell the browser why we are hanging up (it shows this in the header)."""
    try:
        await ws.send_text(json.dumps({"error": message}))
    except Exception:
        pass


def _parse_command(text: str) -> dict:
    """A control message from the browser; anything malformed is ignored."""
    try:
        cmd = json.loads(text)
    except ValueError:
        return {}
    return cmd if isinstance(cmd, dict) else {}


@app.websocket("/ws/recognize")
async def ws_recognize(ws: WebSocket):
    """Browser streams JPEG frames (binary) + JSON control messages; we run the
    recognizer and stream telemetry back. The browser owns the camera."""
    if not await accept_local(ws):
        return
    loop = asyncio.get_event_loop()
    rec: Recognizer | None = None
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            if msg.get("text") is not None:
                cmd = _parse_command(msg["text"])
                kind = cmd.get("cmd")
                if kind == "config":
                    if rec is not None:
                        old, rec = rec, None
                        await loop.run_in_executor(None, old.close)
                    try:
                        rec = await loop.run_in_executor(
                            None,
                            lambda: Recognizer(
                                CONFIG_PATH, DATASET_PATH,
                                dry_run=bool(cmd.get("dry_run", True)),
                                enable_mouse=bool(cmd.get("mouse", True)),
                                enable_face=bool(cmd.get("face", True)),
                            ),
                        )
                    except Exception as e:
                        log.exception("recogniser failed to start")
                        await _send_error(ws, f"recogniser failed to start: {e}")
                        break
                    manager.live = True
                    manager.live_flags = {
                        "dry_run": bool(cmd.get("dry_run", True)),
                        "mouse": bool(cmd.get("mouse", True)),
                        "face": bool(cmd.get("face", True)),
                    }
                    await ws.send_text(json.dumps({"ready": True}))
                elif rec is None:
                    continue
                elif kind == "mode":
                    rec.set_mode(cmd.get("mode", "run"))
                elif kind == "capture":
                    label = str(cmd.get("label", "")).strip()
                    if label:
                        rec.capture(label)
                elif kind == "save":
                    counts = await loop.run_in_executor(None, rec.save)
                    await ws.send_text(json.dumps({"saved": counts}))
                continue

            if msg.get("bytes") is not None and rec is not None:
                frame = await loop.run_in_executor(None, Recognizer.decode, msg["bytes"])
                if frame is None:
                    continue
                telem = await loop.run_in_executor(None, rec.process, frame)
                manager.last_pose = telem.get("pose")
                manager.last_expression = telem.get("expression")
                await ws.send_text(json.dumps(telem))
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        pass  # socket already closed by the client mid-send
    except Exception as e:
        log.exception("recognise socket failed")
        await _send_error(ws, f"recogniser error: {e}")
    finally:
        manager.live = False
        manager.live_flags = {}
        if rec is not None:
            await loop.run_in_executor(None, rec.close)


@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    """Browser streams complete spoken utterances (16 kHz mono int16 PCM, binary);
    we transcribe locally with faster-whisper and route to a command or dictation
    action. JSON control messages set dry_run + mode."""
    if not await accept_local(ws):
        return
    loop = asyncio.get_event_loop()
    cfg = Config.load(CONFIG_PATH)
    router: VoiceRouter | None = None
    mode = "command"
    manager.voice_live = True
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            if msg.get("text") is not None:
                cmd = _parse_command(msg["text"])
                if cmd.get("cmd") == "config":
                    mode = cmd.get("mode", "command")
                    router = VoiceRouter(
                        cfg.voice_commands, cfg.combined,
                        dry_run=bool(cmd.get("dry_run", True)),
                        workflows=cfg.workflows,
                    )
                    if manager._transcriber is None:
                        await ws.send_text(json.dumps(
                            {"loading": "loading speech model (first run downloads ~150 MB)"}))
                    try:
                        await loop.run_in_executor(None, manager.get_transcriber)  # warm
                    except Exception as e:
                        log.exception("speech model failed to load")
                        await _send_error(ws, (
                            "speech model failed to load. The first use downloads it "
                            f"(~150 MB), so it needs internet once. Detail: {e}"))
                        break
                    await ws.send_text(json.dumps({"ready": True}))
                elif cmd.get("cmd") == "mode":
                    mode = cmd.get("mode", "command")
                continue

            if msg.get("bytes") is not None and router is not None:
                pcm = np.frombuffer(msg["bytes"], dtype=np.int16).astype(np.float32) / 32768.0
                text = await loop.run_in_executor(
                    None, lambda: manager.get_transcriber().transcribe(pcm)
                )
                if text:
                    result = await loop.run_in_executor(
                        None, router.route, text,
                        {"mode": mode, "gesture": manager.last_pose,
                         "expression": manager.last_expression, "source": "voice"},
                    )
                    await ws.send_text(json.dumps({
                        "transcript": text, "result": result, "mode": mode,
                        "t": time.time(),
                    }))
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        pass  # socket already closed by the client mid-send
    except Exception as e:
        log.exception("voice socket failed")
        await _send_error(ws, f"voice error: {e}")
    finally:
        manager.voice_live = False


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    if not await accept_local(ws):
        return
    send_video = False
    try:
        while True:
            # Non-blocking check for client control messages (toggle video).
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=0.001)
                try:
                    send_video = bool(json.loads(msg).get("video", send_video))
                except Exception:
                    pass
            except asyncio.TimeoutError:
                pass

            latest, events = manager.snapshot()
            payload = {
                "running": manager.running,
                "events": events,
            }
            if latest:
                payload.update({k: latest.get(k) for k in (
                    "pose", "confidence", "hold", "stable_frames", "committed",
                    "listening", "mode", "mic_rms", "sequence_progress",
                    "hands", "handedness",
                    "recording", "capture_label", "capturing", "counts",
                )})
                if send_video and latest.get("frame_bgr") is not None:
                    payload["frame"] = _encode_frame(latest["frame_bgr"])
            await ws.send_text(json.dumps(payload))
            await asyncio.sleep(0.05)  # ~20 Hz
    except WebSocketDisconnect:
        return
    except Exception:
        return


@app.get("/healthz")
def healthz():
    return JSONResponse({"ok": True})


# ----------------------------------------------------------------- static
# Mounted last: a "/" mount matches every path, so any route added after it
# (like /healthz) would be unreachable.
if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")


def request_camera_access(timeout: float = 60.0) -> str:
    """Request macOS camera + mic authorization on the MAIN thread via
    AVFoundation, pumping the run loop so the system dialog can appear and
    resolve. Returns 'authorized' | 'denied' | 'unavailable'.

    The engine captures from a worker thread, where the auth dialog can't be
    presented — so we get permission here, up front, once."""
    try:
        import AVFoundation
        from Foundation import NSDate, NSDefaultRunLoopMode, NSRunLoop
    except Exception:
        return "unavailable"

    def _req(media) -> bool:
        st = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(media)
        if st == 3:
            return True
        if st in (1, 2):  # restricted / denied
            return False
        done: dict = {}
        AVFoundation.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
            media, lambda granted: done.update(g=bool(granted))
        )
        rl = NSRunLoop.currentRunLoop()
        end = time.monotonic() + timeout
        while "g" not in done and time.monotonic() < end:
            rl.runMode_beforeDate_(
                NSDefaultRunLoopMode, NSDate.dateWithTimeIntervalSinceNow_(0.1)
            )
        return done.get("g", False)

    cam = _req(AVFoundation.AVMediaTypeVideo)
    _req(AVFoundation.AVMediaTypeAudio)  # mic too (for voice); don't block on it
    return "authorized" if cam else "denied"


def prime_camera(index: int = 0) -> bool:
    """Warm the camera on the main thread after auth (helps first worker open)."""
    try:
        cap = cv2.VideoCapture(index)
        ok = cap.isOpened()
        if ok:
            cap.read()
        cap.release()
        return ok
    except Exception:
        return False


def serve(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> None:
    """Start the console. The camera is captured in the BROWSER (clean
    getUserMedia permission), so the server needs no camera access itself —
    only Accessibility permission for the host app if you run non-dry actions
    (keystrokes/mouse)."""
    import uvicorn
    if host not in LOOPBACK_HOSTS:
        raise ValueError(
            f"refusing to bind to {host!r}: the console can run shell commands, "
            "so it only listens on 127.0.0.1")
    configure_origins(port)
    print(f"handsign console → http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


def main():
    serve()


if __name__ == "__main__":
    main()
