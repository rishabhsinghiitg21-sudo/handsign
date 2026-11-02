import { useState } from "react";
import { Play, Square, FlaskConical, Mouse, Zap, Mic, MicOff } from "lucide-react";
import type { Status } from "../lib/api";
import type { CameraController } from "../lib/camera";
import type { VoiceController } from "../lib/voice";

export function CommandBar({
  cam, voice, status, onChanged,
}: {
  cam: CameraController;
  voice: VoiceController;
  status: Status | null;
  onChanged: () => void;
}) {
  const [dryRun, setDryRun] = useState(true);
  const [mouse, setMouse] = useState(true);

  const engage = async () => {
    cam.setMode?.("run");
    await cam.start({ dry_run: dryRun, mouse });
    onChanged();
  };
  const disengage = () => { cam.stop(); onChanged(); };
  const toggleVoice = async () => {
    if (voice.listening) { voice.stop(); }
    else { await voice.start({ dry_run: dryRun, mode: voice.mode }); }
    onChanged();
  };

  return (
    <footer className="flex items-center gap-2 border-t border-hair bg-surface/90 px-4 py-2">
      {!cam.streaming ? (
        <button className="btn btn-active" onClick={engage}>
          <Play size={13} /> Engage
        </button>
      ) : (
        <button className="btn" onClick={disengage}>
          <Square size={13} /> Disengage
        </button>
      )}

      <div className="mx-2 h-5 w-px bg-hair" />

      <button className={`btn ${dryRun ? "btn-active" : ""}`} onClick={() => setDryRun((v) => !v)}
        disabled={cam.streaming} title="Recognize & display, execute nothing">
        <FlaskConical size={13} /> Dry-Run
      </button>
      <button className={`btn ${mouse ? "btn-active" : ""}`} onClick={() => setMouse((v) => !v)}
        disabled={cam.streaming}>
        <Mouse size={13} /> Mouse
      </button>

      <div className="mx-2 h-5 w-px bg-hair" />

      <button className={`btn ${voice.listening ? "btn-active" : ""}`} onClick={toggleVoice}>
        {voice.listening ? <Mic size={13} /> : <MicOff size={13} />} Voice
      </button>
      <button className="btn" onClick={() => voice.setMode(voice.mode === "command" ? "dictation" : "command")}
        title="Switch between firing commands and typing what you say">
        {voice.mode === "command" ? "CMD" : "DICTATE"}
      </button>

      {cam.streaming && !dryRun && (
        <span className="flex items-center gap-1 tac-label text-warn animate-pulse2">
          <Zap size={12} /> LIVE — actions firing (needs Accessibility permission)
        </span>
      )}

      <div className="ml-auto flex items-center gap-3 tac-label">
        <span className="text-secondary">{status?.gestures.length ?? 0} RECORDED</span>
        <span className="text-dim">
          {cam.streaming ? (dryRun ? "DRY-RUN" : "LIVE") : "READY"}
        </span>
      </div>
    </footer>
  );
}
