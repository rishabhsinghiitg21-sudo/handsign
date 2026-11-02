// Browser webcam capture → stream JPEG frames to the Python recognizer over WS,
// receive recognition telemetry back. The browser owns the camera (clean
// getUserMedia permission), so this works without any macOS permission hacks.
import { useCallback, useEffect, useRef, useState } from "react";
import type { FireEvent, Telemetry } from "./api";

const SEND_W = 480; // downscaled width sent to the backend
const FPS = 15;

export interface CameraController {
  stream: MediaStream | null;
  telemetry: Telemetry | null;
  log: FireEvent[];
  streaming: boolean;
  ready: boolean;
  error: string | null;
  start: (flags: { dry_run: boolean; mouse: boolean; mode?: "run" | "record" }) => Promise<void>;
  stop: () => void;
  setMode: (mode: "run" | "record") => void;
  capture: (label: string) => void;
  save: () => void;
}

export function useCamera(): CameraController {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [log, setLog] = useState<FireEvent[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const inflightRef = useRef(false);

  const sendFrame = useCallback(() => {
    const ws = wsRef.current;
    const video = videoRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN || !video || inflightRef.current) return;
    if (video.videoWidth === 0) return;
    let canvas = canvasRef.current;
    if (!canvas) {
      canvas = document.createElement("canvas");
      canvasRef.current = canvas;
    }
    const h = Math.round((SEND_W * video.videoHeight) / video.videoWidth);
    canvas.width = SEND_W;
    canvas.height = h;
    const ctx = canvas.getContext("2d")!;
    // mirror so backend landmarks match the mirrored (selfie) display
    ctx.save();
    ctx.scale(-1, 1);
    ctx.drawImage(video, -SEND_W, 0, SEND_W, h);
    ctx.restore();
    inflightRef.current = true;
    canvas.toBlob(
      (blob) => {
        if (blob && ws.readyState === WebSocket.OPEN) blob.arrayBuffer().then((b) => ws.send(b));
        inflightRef.current = false;
      },
      "image/jpeg",
      0.6
    );
  }, []);

  const start = useCallback(async (flags: { dry_run: boolean; mouse: boolean; mode?: "run" | "record" }) => {
    setError(null);
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 }, audio: false });
      setStream(s);
      // offscreen video for capture
      let video = videoRef.current;
      if (!video) {
        video = document.createElement("video");
        video.muted = true;
        (video as any).playsInline = true;
        videoRef.current = video;
      }
      video.srcObject = s;
      await video.play();

      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws/recognize`);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;
      ws.onopen = () => {
        const { mode, ...cfgFlags } = flags;
        ws.send(JSON.stringify({ cmd: "config", face: true, ...cfgFlags }));
        if (mode) ws.send(JSON.stringify({ cmd: "mode", mode })); // sent only once open
        setStreaming(true);
        timerRef.current = setInterval(sendFrame, 1000 / FPS);
      };
      ws.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.error) { setError(m.error); return; }  // the server hangs up right after
        if (m.ready) { setReady(true); return; }
        if (m.saved) return;
        setTelemetry(m as Telemetry);
        if (m.events?.length) {
          const fires = (m.events as FireEvent[]).filter((x) => x.kind !== "mouse");
          if (fires.length) setLog((prev) => [...fires, ...prev].slice(0, 120));
        }
      };
      ws.onclose = () => {
        // Server went away (or refused us): release the camera so its light goes off.
        if (wsRef.current === ws) {
          if (timerRef.current) clearInterval(timerRef.current);
          timerRef.current = null;
          wsRef.current = null;
          s.getTracks().forEach((t) => t.stop());
          setStream(null);
          setTelemetry(null);
        }
        setStreaming(false); setReady(false);
      };
    } catch (e: any) {
      setError(e?.message || "camera access denied");
    }
  }, [sendFrame]);

  const stop = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    wsRef.current?.close();
    wsRef.current = null;
    stream?.getTracks().forEach((t) => t.stop());
    if (videoRef.current) videoRef.current.srcObject = null;
    setStream(null);
    setStreaming(false);
    setReady(false);
    setTelemetry(null);
  }, [stream]);

  const sendCmd = (obj: any) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
  };
  const setMode = useCallback((mode: "run" | "record") => sendCmd({ cmd: "mode", mode }), []);
  const capture = useCallback((label: string) => sendCmd({ cmd: "capture", label }), []);
  const save = useCallback(() => sendCmd({ cmd: "save" }), []);

  useEffect(() => () => stop(), []); // cleanup on unmount

  return { stream, telemetry, log, streaming, ready, error, start, stop, setMode, capture, save };
}
