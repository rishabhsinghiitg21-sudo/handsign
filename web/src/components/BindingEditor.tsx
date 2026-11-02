import { useEffect, useState } from "react";
import { Plus, Trash2, Save, X } from "lucide-react";
import { api, type Status } from "../lib/api";
import { ActionInput } from "./ActionInput";
import { RenameInput } from "./RenameInput";
import { renameKey, uniqueName } from "../lib/configEdit";

function Section({ title, children, onAdd }: any) {
  return (
    <div className="panel">
      <div className="panel-head">
        <span>{title}</span>
        {onAdd && (
          <button className="text-accent hover:text-primary" onClick={onAdd} aria-label={`add ${title}`}>
            <Plus size={15} />
          </button>
        )}
      </div>
      <div className="space-y-2 p-3">{children}</div>
    </div>
  );
}

function Slider({ label, value, min, max, step, onChange }: any) {
  return (
    <div className="flex items-center gap-3">
      <span className="tac-label w-40 shrink-0">{label}</span>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="flex-1 accent-accent" />
      <span className="tac-value text-label w-14 text-right">{value}</span>
    </div>
  );
}

export function BindingEditor({ status, onChanged }: { status: Status | null; onChanged: () => void }) {
  const [cfg, setCfg] = useState<any>(null);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const gestures = status?.gesture_names ?? status?.gestures ?? [];

  useEffect(() => { api.getConfig().then(setCfg).catch(() => {}); }, []);
  const mutate = (fn: (c: any) => void) => {
    setCfg((prev: any) => { const next = JSON.parse(JSON.stringify(prev)); fn(next); return next; });
    setDirty(true); setSaved(false); setError(null);
  };
  const save = async () => {
    try {
      await api.putConfig(cfg);
      setDirty(false); setSaved(true); setError(null); onChanged();
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      setSaved(false); setError(e?.message || "save failed");
    }
  };

  if (!cfg) return <div className="tac-label text-dim p-3">loading config…</div>;
  const s = cfg.settings ?? {}; const ms = s.mouse ?? {}; const vs = s.voice ?? {};
  const wfNames = Object.keys(cfg.workflows ?? {});

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base uppercase tracking-widest text-primary">Binding Editor</h2>
        <div className="flex items-center gap-3">
          {error && <span className="tac-label text-alert" role="alert">✕ NOT SAVED: {error}</span>}
          {saved && <span className="tac-label text-ok">✓ SAVED</span>}
          {dirty && <span className="tac-label text-warn">● UNSAVED</span>}
          <button className="btn btn-active" onClick={save} disabled={!dirty}>
            <Save size={13} /> Save Changes
          </button>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 overflow-auto pb-2">
        {/* POSE → ACTION */}
        <Section title="Pose → Action"
          onAdd={() => mutate((c) => {
            const used = Object.keys(c.poses ?? {});
            const free = gestures.find((g: string) => !used.includes(g)) ?? uniqueName("new_pose", used);
            c.poses = { ...(c.poses ?? {}), [free]: { action: { type: "key", value: "" } } };
          })}>
          {Object.entries<any>(cfg.poses ?? {}).map(([name, spec]) => (
            <div key={name} className="flex items-center gap-2">
              <span className="font-display text-label uppercase text-primary w-28 truncate">{name}</span>
              <div className="flex-1"><ActionInput action={spec.action} workflowNames={wfNames} onChange={(a) => mutate((c) => { c.poses[name].action = a; })} /></div>
              <button className="text-dim hover:text-alert" onClick={() => mutate((c) => { delete c.poses[name]; })}><Trash2 size={14} /></button>
            </div>
          ))}
          {Object.keys(cfg.poses ?? {}).length === 0 && <span className="tac-label text-dim">none</span>}
        </Section>

        {/* VOICE COMMANDS */}
        <Section title="Voice Commands"
          onAdd={() => mutate((c) => {
            const name = uniqueName("new command", Object.keys(c.voice_commands ?? {}), " ");
            c.voice_commands = { ...(c.voice_commands ?? {}), [name]: { action: { type: "key", value: "" } } };
          })}>
          {Object.entries<any>(cfg.voice_commands ?? {}).map(([phrase, spec]) => (
            <div key={phrase} className="flex items-center gap-2">
              <RenameInput className="w-32 border border-hair bg-base px-2 py-1 font-mono text-micro text-ok focus:border-accent focus:outline-none"
                value={phrase} taken={Object.keys(cfg.voice_commands)} aria-label="spoken phrase"
                onCommit={(next) => mutate((c) => { c.voice_commands = renameKey(c.voice_commands, phrase, next); })} />
              <div className="flex-1"><ActionInput action={spec.action} workflowNames={wfNames} onChange={(a) => mutate((c) => { c.voice_commands[phrase].action = a; })} /></div>
              <button className="text-dim hover:text-alert" onClick={() => mutate((c) => { delete c.voice_commands[phrase]; })}><Trash2 size={14} /></button>
            </div>
          ))}
        </Section>

        {/* EXPRESSIONS */}
        <Section title="Facial Expression → Action"
          onAdd={() => mutate((c) => {
            const names: string[] = status?.expression_names ?? [];
            const free = names.find((n) => !(c.expressions ?? {})[n]) ?? names[0] ?? "smile";
            c.expressions = { ...(c.expressions ?? {}), [free]: { action: { type: "key", value: "" } } };
          })}>
          {Object.entries<any>(cfg.expressions ?? {}).map(([name, spec]) => (
            <div key={name} className="flex items-center gap-2">
              <select className="w-28 border border-hair bg-base px-1 py-1 font-mono text-micro text-amber focus:outline-none"
                value={name}
                onChange={(e) => mutate((c) => { c.expressions = renameKey(c.expressions, name, e.target.value); })}>
                {(status?.expression_names ?? [name]).map((n) => (
                  <option key={n} value={n} disabled={n !== name && n in (cfg.expressions ?? {})}>{n}</option>
                ))}
              </select>
              <div className="flex-1"><ActionInput action={spec.action} workflowNames={wfNames} onChange={(a) => mutate((c) => { c.expressions[name].action = a; })} /></div>
              <button className="text-dim hover:text-alert" onClick={() => mutate((c) => { delete c.expressions[name]; })}><Trash2 size={14} /></button>
            </div>
          ))}
          {Object.keys(cfg.expressions ?? {}).length === 0 && <span className="tac-label text-dim">none — add one (smile, brows_up, mouth_open, wink…)</span>}
        </Section>

        {/* SEQUENCES */}
        <Section title="Sequences (combos)"
          onAdd={() => mutate((c) => {
            const name = uniqueName("new_combo", Object.keys(c.sequences ?? {}));
            c.sequences = { ...(c.sequences ?? {}), [name]: { steps: [], action: { type: "key", value: "" } } };
          })}>
          {Object.entries<any>(cfg.sequences ?? {}).map(([name, spec]) => (
            <div key={name} className="space-y-1 border-b border-hair/40 pb-2">
              <div className="flex items-center gap-2">
                <RenameInput className="w-28 border border-hair bg-base px-2 py-1 font-mono text-micro text-amber focus:border-accent focus:outline-none"
                  value={name} taken={Object.keys(cfg.sequences)} aria-label="sequence name"
                  onCommit={(next) => mutate((c) => { c.sequences = renameKey(c.sequences, name, next); })} />
                <div className="flex-1"><ActionInput action={spec.action} workflowNames={wfNames} onChange={(a) => mutate((c) => { c.sequences[name].action = a; })} /></div>
                <button className="text-dim hover:text-alert" onClick={() => mutate((c) => { delete c.sequences[name]; })}><Trash2 size={14} /></button>
              </div>
              <div className="flex flex-wrap items-center gap-1">
                {(spec.steps ?? []).map((st: string, idx: number) => (
                  <span key={idx} className="flex items-center gap-1 border border-hair bg-elevated px-1.5 py-0.5 text-micro uppercase text-amber">
                    {st}
                    <button onClick={() => mutate((c) => { c.sequences[name].steps.splice(idx, 1); })}><X size={10} /></button>
                  </span>
                ))}
                <select className="border border-hair bg-base px-1 py-0.5 text-micro text-secondary focus:outline-none"
                  value=""
                  onChange={(e) => { if (e.target.value) mutate((c) => { c.sequences[name].steps.push(e.target.value); }); }}>
                  <option value="">+ step…</option>
                  {gestures.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </div>
            </div>
          ))}
        </Section>

        {/* COMBINED (multi-input) */}
        <Section title="Combined (gesture + expression + voice)"
          onAdd={() => mutate((c) => { c.combined = [...(c.combined ?? []), { action: { type: "key", value: "" } }]; })}>
          {(cfg.combined ?? []).map((cb: any, i: number) => (
            <div key={i} className="space-y-1 border-b border-hair/40 pb-2">
              <div className="flex flex-wrap items-center gap-1">
                <select className="w-28 border border-hair bg-base px-1 py-1 text-micro text-accent focus:outline-none"
                  value={cb.gesture ?? ""}
                  onChange={(e) => mutate((c) => { if (e.target.value) c.combined[i].gesture = e.target.value; else delete c.combined[i].gesture; })}>
                  <option value="">pose</option>
                  {gestures.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
                <span className="text-dim">+</span>
                <select className="w-32 border border-hair bg-base px-1 py-1 text-micro text-amber focus:outline-none"
                  value={cb.expression ?? ""}
                  onChange={(e) => mutate((c) => { if (e.target.value) c.combined[i].expression = e.target.value; else delete c.combined[i].expression; })}>
                  <option value="">face</option>
                  {(status?.expression_names ?? []).map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
                <span className="text-dim">+</span>
                <input className="w-24 border border-hair bg-base px-2 py-1 text-micro text-ok focus:border-accent focus:outline-none"
                  placeholder="phrase" value={cb.phrase ?? ""}
                  onChange={(e) => mutate((c) => { if (e.target.value) c.combined[i].phrase = e.target.value; else delete c.combined[i].phrase; })} />
                <button className="ml-auto text-dim hover:text-alert" onClick={() => mutate((c) => { c.combined.splice(i, 1); })}><Trash2 size={14} /></button>
              </div>
              <div className="flex flex-wrap items-center gap-1">
                <span className="tac-label text-dim">two hands:</span>
                {[0, 1].map((hi) => (
                  <select key={hi} className="w-28 border border-hair bg-base px-1 py-1 text-micro text-accent focus:outline-none"
                    value={cb.hands?.[hi] ?? ""}
                    onChange={(e) => mutate((c) => {
                      const arr = [...(c.combined[i].hands ?? ["", ""])];
                      arr[hi] = e.target.value;
                      const clean = arr.filter(Boolean);
                      if (clean.length) c.combined[i].hands = arr.map((x) => x || "");
                      if (clean.length === 0) delete c.combined[i].hands;
                    })}>
                    <option value="">{hi === 0 ? "hand A" : "hand B"}</option>
                    {gestures.map((g) => <option key={g} value={g}>{g}</option>)}
                  </select>
                ))}
              </div>
              <ActionInput action={cb.action} workflowNames={wfNames} onChange={(a) => mutate((c) => { c.combined[i].action = a; })} />
            </div>
          ))}
          {(cfg.combined ?? []).length === 0 && <span className="tac-label text-dim">none — e.g. thumbs_up + smile → "approved!"</span>}
        </Section>

        {/* SETTINGS */}
        <Section title="Tuning">
          <Slider label="min_confidence" value={s.min_confidence ?? 0.7} min={0.3} max={0.95} step={0.01}
            onChange={(v: number) => mutate((c) => { (c.settings ??= {}).min_confidence = v; })} />
          <Slider label="max_distance" value={s.max_distance ?? 0.55} min={0.1} max={1.5} step={0.01}
            onChange={(v: number) => mutate((c) => { (c.settings ??= {}).max_distance = v; })} />
          <Slider label="stable_frames" value={s.stable_frames ?? 8} min={2} max={20} step={1}
            onChange={(v: number) => mutate((c) => { (c.settings ??= {}).stable_frames = v; })} />
          <Slider label="cooldown (s)" value={s.cooldown ?? 1} min={0} max={3} step={0.1}
            onChange={(v: number) => mutate((c) => { (c.settings ??= {}).cooldown = v; })} />
          <div className="my-1 border-t border-hair" />
          <Slider label="mouse.pinch_threshold" value={ms.pinch_threshold ?? 0.6} min={0.1} max={1.2} step={0.01}
            onChange={(v: number) => mutate((c) => { ((c.settings ??= {}).mouse ??= {}).pinch_threshold = v; })} />
          <Slider label="mouse.smoothing" value={ms.smoothing ?? 0.5} min={0} max={0.9} step={0.05}
            onChange={(v: number) => mutate((c) => { ((c.settings ??= {}).mouse ??= {}).smoothing = v; })} />
          <Slider label="voice.energy_threshold" value={vs.energy_threshold ?? 0.012} min={0.002} max={0.08} step={0.001}
            onChange={(v: number) => mutate((c) => { ((c.settings ??= {}).voice ??= {}).energy_threshold = v; })} />
        </Section>
      </div>
    </div>
  );
}
