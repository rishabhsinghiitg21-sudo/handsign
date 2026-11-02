import { Video, VideoOff, Zap, Hand, Smile, Mic, Combine } from "lucide-react";
import type { Status } from "../lib/api";
import type { CameraController } from "../lib/camera";
import type { VoiceController } from "../lib/voice";
import { Viewport } from "./Viewport";

function Bar({ value, max = 1, color = "bg-accent" }: { value: number; max?: number; color?: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="h-1.5 w-full border border-hair bg-base">
      <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function Channel({ icon: Icon, label, value, pct, sub, active, color }: any) {
  return (
    <div className={`flex flex-col gap-1.5 border border-hair p-3 ${active ? "bg-elevated/70" : "bg-base/40"}`}>
      <span className={`flex items-center gap-1.5 tac-label ${active ? color : "text-secondary"}`}>
        <Icon size={13} /> {label}
      </span>
      <span className="font-display text-[20px] uppercase leading-none text-primary truncate">
        {value || "—"}
      </span>
      <Bar value={pct} color={active ? color.replace("text-", "bg-") : "bg-hair"} />
      <span className="tac-label text-dim tabular-nums">{sub}</span>
    </div>
  );
}

export function LiveOps({
  cam, voice, status, video, onToggleVideo,
}: {
  cam: CameraController;
  voice: VoiceController;
  status: Status | null;
  video: boolean;
  onToggleVideo: () => void;
}) {
  const t = cam.telemetry;
  const conf = t?.confidence ?? 0;
  const hold = t?.hold ?? 0;
  const stable = t?.stable_frames ?? 8;
  const exprI = t?.expression_intensity ?? 0;
  const combo = t?.active_combo;
  const lastFire = t?.events?.find((e) => e.kind !== "error" && e.kind !== "mouse");
  const handPoses = (t?.hand_poses ?? []).filter((h) => h.pose);
  const comboParts = combo
    ? [...(combo.hands ?? []), combo.gesture, combo.expression].filter(Boolean)
    : [];

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base uppercase tracking-widest text-primary">Live Ops</h2>
        <button className="btn" onClick={onToggleVideo} aria-pressed={video}>
          {video ? <Video size={13} /> : <VideoOff size={13} />}
          {video ? "Video On" : "Vector Only"}
        </button>
      </div>

      <Viewport stream={cam.stream} telemetry={t} video={video} streaming={cam.streaming} />

      {/* MULTI-INPUT MONITOR — all three channels at once */}
      <div className="panel brackets">
        <span className="bk-bl" /><span className="bk-br" />
        <div className="panel-head">
          <span>Multi-Input Monitor</span>
          <span className="text-dim">DRY-RUN SAFE · LIVE CAPTURE</span>
        </div>

        <div className="grid grid-cols-3 gap-2 p-3">
          <div className={`flex flex-col gap-1.5 border border-hair p-3 ${handPoses.length ? "bg-elevated/70" : "bg-base/40"}`}>
            <span className={`flex items-center gap-1.5 tac-label ${handPoses.length ? "text-accent" : "text-secondary"}`}>
              <Hand size={13} /> Gesture {handPoses.length === 2 ? "· 2 HANDS" : ""}
            </span>
            {handPoses.length === 0 ? (
              <span className="font-display text-[20px] uppercase text-primary">—</span>
            ) : (
              handPoses.map((h, i) => (
                <div key={i} className="flex flex-col gap-0.5">
                  <span className="font-display text-[16px] uppercase leading-none text-primary truncate">
                    <span className="text-dim">{h.hand[0]}:</span> {h.pose}
                  </span>
                  <Bar value={h.confidence} color="bg-accent" />
                </div>
              ))
            )}
            <span className="tac-label text-dim tabular-nums">hold {hold}/{stable}</span>
          </div>
          <Channel icon={Smile} label="Expression" color="text-amber"
            value={t?.expression ?? (t?.face_present ? "neutral" : null)} pct={exprI}
            active={!!t?.expression}
            sub={`intensity ${(exprI * 100).toFixed(0)}%`} />
          <Channel icon={Mic} label="Voice" color="text-ok"
            value={voice.listening ? (voice.last?.transcript ?? "…") : null} pct={voice.level}
            active={voice.listening}
            sub={voice.listening
              ? (voice.ready ? `${voice.mode} · level ${(voice.level * 100).toFixed(0)}%`
                             : voice.note ?? "starting…")
              : "mic off"} />
        </div>

        {/* ACTIVE COMBO — what the current simultaneous inputs mean */}
        {combo && (
          <div className="flex items-center gap-2 border-t border-hair bg-elevated/60 px-3 py-2 text-ok">
            <Combine size={15} className="animate-pulse2" />
            <span className="font-display uppercase tracking-wider">Combination active:</span>
            <span className="font-mono text-primary">{comboParts.join(" + ")}</span>
            <span className="font-mono text-secondary">→ {combo.action_type}:{combo.action_value}</span>
          </div>
        )}

        {/* WOULD FIRE / DID FIRE */}
        <div className="border-t border-hair px-3 py-2">
          {lastFire ? (
            <div className="flex items-center gap-2 text-ok">
              <Zap size={15} className="animate-pulse2" />
              <span className="font-display uppercase tracking-wider">
                {lastFire.dry_run ? "Would fire:" : "Fired:"}
              </span>
              <span className="font-mono text-primary">{lastFire.name}</span>
              {lastFire.action_value && (
                <span className="font-mono text-secondary">→ {lastFire.action_type}:{lastFire.action_value}</span>
              )}
              {lastFire.dry_run && <span className="ml-auto tac-label text-warn">DRY-RUN</span>}
            </div>
          ) : (
            <div className="tac-label text-dim">▣ AWAITING INPUT — gesture, expression, or voice (combine them for distinct actions)</div>
          )}
        </div>
      </div>
    </div>
  );
}
