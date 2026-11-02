import { useEffect, useMemo, useState } from "react";
import { Search, Hand, Layers, Mic, Combine, MousePointer2, Smile } from "lucide-react";
import { api } from "../lib/api";
import { GesturePreview } from "./GesturePreview";

type Kind = "POSE" | "SEQUENCE" | "VOICE" | "EXPRESSION" | "COMBINED" | "PTT" | "MOUSE";

interface Binding {
  kind: Kind;
  trigger: string;
  detail: string;
  action: string;
  preview: string[]; // gesture labels to animate (empty = no hand preview)
}

const KIND_META: Record<Kind, { icon: any; color: string }> = {
  POSE: { icon: Hand, color: "text-accent" },
  SEQUENCE: { icon: Layers, color: "text-amber" },
  VOICE: { icon: Mic, color: "text-ok" },
  EXPRESSION: { icon: Smile, color: "text-amber" },
  COMBINED: { icon: Combine, color: "text-accent" },
  PTT: { icon: Mic, color: "text-ok" },
  MOUSE: { icon: MousePointer2, color: "text-secondary" },
};

function toBindings(cfg: any): Binding[] {
  const out: Binding[] = [];
  const act = (a: any) => (a ? `${a.type}:${a.value}` : "—");
  for (const [name, spec] of Object.entries<any>(cfg.poses ?? {}))
    out.push({ kind: "POSE", trigger: name, detail: "static pose", action: act(spec.action), preview: [name] });
  for (const [name, spec] of Object.entries<any>(cfg.sequences ?? {}))
    out.push({ kind: "SEQUENCE", trigger: name, detail: (spec.steps ?? []).join(" ▸ "), action: act(spec.action), preview: spec.steps ?? [] });
  for (const [phrase, spec] of Object.entries<any>(cfg.voice_commands ?? {}))
    out.push({ kind: "VOICE", trigger: `"${phrase}"`, detail: "spoken command", action: act(spec.action), preview: [] });
  for (const [name, spec] of Object.entries<any>(cfg.expressions ?? {}))
    out.push({ kind: "EXPRESSION", trigger: name, detail: "facial expression", action: act(spec.action), preview: [] });
  for (const c of (cfg.combined ?? []) as any[]) {
    const parts = [
      ...(c.hands ?? []).map((h: string) => `✋${h}`),
      c.gesture, c.expression, c.phrase ? `"${c.phrase}"` : null,
    ].filter(Boolean);
    const preview = c.hands ?? (c.gesture ? [c.gesture] : []);
    out.push({ kind: "COMBINED", trigger: parts.join(" + "), detail: c.hands ? "two hands" : "all at once", action: act(c.action), preview });
  }
  for (const [pose, spec] of Object.entries<any>(cfg.push_to_talk ?? {}))
    out.push({ kind: "PTT", trigger: pose, detail: "push-to-talk", action: `listen → ${spec.mode}`, preview: [pose] });
  const m = cfg.settings?.mouse ?? {};
  if (m.gesture) out.push({ kind: "MOUSE", trigger: m.gesture, detail: "hold = cursor + pinch-click", action: "mouse:move/click", preview: [m.gesture] });
  if (m.scroll_gesture) out.push({ kind: "MOUSE", trigger: m.scroll_gesture, detail: "hold = scroll", action: "mouse:scroll", preview: [m.scroll_gesture] });
  return out;
}

export function ActionRepository() {
  const [cfg, setCfg] = useState<any>(null);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Kind | "ALL">("ALL");

  useEffect(() => { api.getConfig().then(setCfg).catch(() => {}); }, []);

  const bindings = useMemo(() => (cfg ? toBindings(cfg) : []), [cfg]);
  const filtered = bindings.filter(
    (b) =>
      (filter === "ALL" || b.kind === filter) &&
      (b.trigger.toLowerCase().includes(q.toLowerCase()) ||
        b.action.toLowerCase().includes(q.toLowerCase()))
  );

  const kinds: (Kind | "ALL")[] = ["ALL", "POSE", "SEQUENCE", "EXPRESSION", "VOICE", "COMBINED", "PTT", "MOUSE"];

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base uppercase tracking-widest text-primary">
          Action Repository
        </h2>
        <span className="tac-label text-dim">{filtered.length} / {bindings.length} bindings</span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-2 border border-hair bg-base px-2">
          <Search size={13} className="text-dim" />
          <input
            className="bg-transparent py-1.5 font-mono text-data text-primary focus:outline-none"
            placeholder="search trigger / action"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        {kinds.map((k) => (
          <button
            key={k}
            className={`btn ${filter === k ? "btn-active" : ""}`}
            onClick={() => setFilter(k)}
          >
            {k}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3 overflow-auto pb-2">
        {filtered.map((b, i) => {
          const M = KIND_META[b.kind];
          const Icon = M.icon;
          return (
            <div key={i} className="panel flex gap-3 p-3">
              {b.preview.length ? (
                <GesturePreview labels={b.preview} size={92} color={b.kind === "SEQUENCE" ? "#F5A623" : "#38BDF8"} />
              ) : (
                <div className="flex h-[92px] w-[92px] items-center justify-center border border-hair bg-base">
                  <Icon size={28} className={M.color} />
                </div>
              )}
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <span className={`flex items-center gap-1 tac-label ${M.color}`}>
                  <Icon size={12} /> {b.kind}
                </span>
                <span className="font-display text-base uppercase text-primary truncate">
                  {b.trigger}
                </span>
                <span className="tac-label text-dim truncate">{b.detail}</span>
                <span className="mt-auto font-mono text-micro text-secondary truncate">
                  → {b.action}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
