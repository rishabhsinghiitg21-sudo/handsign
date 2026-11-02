import { useState } from "react";
import { Circle, Save, Trash2, Camera, Crosshair, Gauge } from "lucide-react";
import { api, type Status } from "../lib/api";
import type { CameraController } from "../lib/camera";
import { Viewport } from "./Viewport";
import { GesturePreview } from "./GesturePreview";

export function GestureLibrary({
  cam, status, video, onChanged,
}: {
  cam: CameraController;
  status: Status | null;
  video: boolean;
  onChanged: () => void;
}) {
  const [recording, setRecording] = useState(false);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [calib, setCalib] = useState<string | null>(null);
  const counts = cam.telemetry?.counts ?? status?.sample_counts ?? {};
  const gestures = Object.keys(status?.sample_counts ?? {}).sort();
  const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, "_");

  const startRec = async () => {
    setBusy(true);
    try {
      if (cam.streaming) cam.setMode("record");
      else await cam.start({ dry_run: true, mouse: false, mode: "record" });
      setRecording(true);
    } finally { setBusy(false); }
  };
  const capture = () => {
    const l = norm(label);
    if (!l) return alert("name the gesture first");
    if (!cam.ready) return alert("the recogniser is still starting, try again in a moment");
    setLabel(l);
    cam.capture(l);
  };
  const finish = async () => {
    cam.save();
    setTimeout(() => { cam.stop(); setRecording(false); onChanged(); }, 400);
  };
  const remove = async (g: string) => {
    if (!confirm(`Delete all samples for "${g}"?`)) return;
    await api.deleteLabel(g); onChanged();
  };
  const runCalibration = async () => {
    setCalib("running…");
    try { setCalib((await api.calibrateClassifier()).report); }
    catch (e: any) { setCalib("error: " + e.message); }
  };

  if (recording) {
    const curCount = label ? counts[norm(label)] ?? 0 : 0;
    return (
      <div className="flex h-full flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-base uppercase tracking-widest text-primary">Record Gesture</h2>
          <span className="flex items-center gap-2 tac-label text-alert animate-pulse2">
            <Circle size={10} fill="currentColor" /> REC
          </span>
        </div>
        <Viewport stream={cam.stream} telemetry={cam.telemetry} video={video} streaming={cam.streaming} />
        <div className="panel">
          <div className="panel-head"><span>Capture</span>
            <span className={cam.telemetry?.capturing ? "text-ok animate-pulse2" : "text-dim"}>
              {cam.telemetry?.capturing ? "● CAPTURING" : "ready"}
            </span>
          </div>
          <div className="flex flex-wrap items-end gap-3 p-3">
            <div className="flex flex-col gap-1">
              <span className="tac-label">Gesture name</span>
              <input className="border border-hair bg-base px-2 py-1.5 font-mono text-data text-primary focus:border-accent focus:outline-none"
                placeholder="e.g. point, fist, tiger" value={label} onChange={(e) => setLabel(e.target.value)} />
            </div>
            <button className="btn btn-active" onClick={capture}><Crosshair size={13} /> Capture Burst</button>
            <div className="tac-value text-label">samples: <span className="text-accent">{curCount}</span></div>
            <button className="btn ml-auto" onClick={finish}><Save size={13} /> Save &amp; Finish</button>
          </div>
          <div className="border-t border-hair px-3 py-2 tac-label text-dim">
            Hold the pose in frame → Capture Burst (~1.5s). Repeat from a few angles (~60 samples).
            Rename to record another gesture in the same session.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base uppercase tracking-widest text-primary">Gesture Library</h2>
        <div className="flex items-center gap-2">
          <input className="border border-hair bg-base px-2 py-1.5 font-mono text-data text-primary focus:border-accent focus:outline-none"
            placeholder="new gesture name" value={label} onChange={(e) => setLabel(e.target.value)} />
          <button className="btn btn-active" onClick={startRec} disabled={busy}>
            <Camera size={13} /> Record New
          </button>
          <button className="btn" onClick={runCalibration} title="Auto-tune thresholds">
            <Gauge size={13} /> Calibrate
          </button>
        </div>
      </div>

      {calib && (
        <div className="panel">
          <div className="panel-head"><span>Calibration Report</span>
            <button className="text-dim hover:text-primary" onClick={() => setCalib(null)}>✕</button>
          </div>
          <pre className="overflow-auto p-3 font-mono text-micro text-secondary whitespace-pre-wrap">{calib}</pre>
        </div>
      )}

      {gestures.length === 0 ? (
        <div className="panel brackets flex flex-1 flex-col items-center justify-center gap-2">
          <span className="bk-bl" /><span className="bk-br" />
          <span className="font-display uppercase tracking-widest text-secondary">No gestures yet</span>
          <span className="tac-label text-dim">Name one above and hit “Record New”.</span>
          <span className="tac-label text-dim">The seven built-in poses work without recording anything.</span>
        </div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
          {gestures.map((g) => (
            <div key={g} className="panel p-3 flex flex-col items-center gap-2">
              <GesturePreview labels={[g]} size={130} />
              <div className="flex w-full items-center justify-between">
                <span className="font-display uppercase text-label text-primary">{g}</span>
                <button className="text-dim hover:text-alert" onClick={() => remove(g)} aria-label={`delete ${g}`}>
                  <Trash2 size={14} />
                </button>
              </div>
              <span className="tac-label text-dim">{status?.sample_counts[g]} samples</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
