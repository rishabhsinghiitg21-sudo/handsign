import type { FireEvent, Telemetry } from "../lib/api";
import type { VoiceController } from "../lib/voice";
import { Mic, Volume2 } from "lucide-react";

const KIND_COLOR: Record<string, string> = {
  pose: "text-accent",
  sequence: "text-amber",
  voice: "text-ok",
  expression: "text-amber",
  mouse: "text-secondary",
  error: "text-alert",
};

export function TelemetryRail({
  telemetry, log, voice,
}: {
  telemetry: Telemetry | null;
  log: FireEvent[];
  voice: VoiceController;
}) {
  const meter = Math.round((voice.level ?? 0) * 100);
  const seq = telemetry?.sequence_progress ?? [];

  // unified, time-sorted capture log across all channels
  const merged = [
    ...log.map((e) => ({
      t: e.t ?? 0, kind: e.kind, name: e.name,
      detail: e.action_value ? `${e.action_type}:${e.action_value}${e.dry_run ? " (dry)" : ""}` : e.detail,
    })),
    ...voice.log.map((v) => ({
      t: v.t, kind: "voice", name: `"${v.transcript}"`, detail: v.result,
    })),
  ].sort((a, b) => b.t - a.t).slice(0, 120);

  return (
    <aside className="flex min-h-0 flex-col gap-3 overflow-auto border-l border-hair bg-surface/60 p-3">
      {/* voice */}
      <div className="panel">
        <div className="panel-head">
          <span>Voice</span>
          {voice.listening ? (
            <span className="flex items-center gap-1 text-ok animate-pulse2">
              <Mic size={12} /> LISTENING
            </span>
          ) : (
            <span className="text-dim">MIC OFF</span>
          )}
        </div>
        <div className="space-y-2 p-3">
          <div className="flex items-center justify-between">
            <span className="tac-label">Mode</span>
            <span className="tac-value font-display uppercase text-accent">
              {voice.listening ? voice.mode : "—"}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Volume2 size={13} className="text-secondary" />
            <div className="h-2 flex-1 border border-hair bg-base">
              <div className={`h-full ${meter > 60 ? "bg-ok" : "bg-accent"}`} style={{ width: `${meter}%` }} />
            </div>
          </div>
          {voice.last && (
            <div className="border-t border-hair pt-2">
              <div className="tac-label text-dim">last heard</div>
              <div className="font-mono text-micro text-primary">"{voice.last.transcript}"</div>
              <div className="font-mono text-micro text-secondary truncate">→ {voice.last.result}</div>
            </div>
          )}
        </div>
      </div>

      {/* sequence tracker */}
      <div className="panel">
        <div className="panel-head"><span>Sequence Buffer</span></div>
        <div className="flex flex-wrap gap-1 p-3 min-h-[44px]">
          {seq.length ? (
            seq.map((s, i) => (
              <span
                key={i}
                className="border border-hair bg-elevated px-2 py-0.5 text-micro uppercase text-amber"
              >
                {s}
              </span>
            ))
          ) : (
            <span className="tac-label text-dim">— no combo in progress</span>
          )}
        </div>
      </div>

      {/* unified event log: gestures + expressions + sequences + combined + voice */}
      <div className="panel flex min-h-0 flex-1 flex-col">
        <div className="panel-head">
          <span>Capture Log</span>
          <span className="text-dim">{merged.length}</span>
        </div>
        <div className="flex-1 overflow-auto p-2 font-mono text-micro" aria-live="polite">
          {merged.length === 0 && (
            <div className="tac-label text-dim p-1">— nothing captured yet</div>
          )}
          {merged.map((e, i) => (
            <div key={i} className="flex gap-2 border-b border-hair/40 py-1">
              <span className="text-dim tabular-nums">
                {new Date(e.t * 1000).toLocaleTimeString("en-GB")}
              </span>
              <span className={`uppercase ${KIND_COLOR[e.kind] ?? "text-secondary"}`}>{e.kind}</span>
              <span className="text-primary truncate">{e.name}</span>
              {e.detail && <span className="ml-auto text-secondary truncate">{e.detail}</span>}
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
