import { useEffect, useState } from "react";
import { Plus, Trash2, Save, Play, Workflow as WorkflowIcon } from "lucide-react";
import { api } from "../lib/api";
import { ActionInput } from "./ActionInput";
import { RenameInput } from "./RenameInput";
import { renameWorkflow, uniqueName, workflowUsers } from "../lib/configEdit";

export function Workflows({ onChanged }: { onChanged: () => void }) {
  const [cfg, setCfg] = useState<any>(null);
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const [ran, setRan] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.getConfig().then(setCfg).catch(() => {}); }, []);
  const mutate = (fn: (c: any) => void) => {
    setCfg((prev: any) => { const next = JSON.parse(JSON.stringify(prev)); if (!next.workflows) next.workflows = {}; fn(next); return next; });
    setDirty(true); setSaved(false); setError(null);
  };
  const save = async () => {
    try {
      await api.putConfig(cfg);
      setDirty(false); setSaved(true); setError(null); onChanged();
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) { setSaved(false); setError(`not saved: ${e?.message || "save failed"}`); }
  };
  const remove = (name: string) => {
    // Deleting a workflow that something still points to would leave a dead binding: block it.
    const users = workflowUsers(cfg, name);
    if (users.length) {
      setError(`can't delete "${name}", it is used by ${users.join(", ")}. Change those bindings first.`);
      return;
    }
    mutate((c) => { delete c.workflows[name]; });
  };
  const run = async (name: string) => {
    // Run is a real run: it ignores the Dry-Run switch in the command bar.
    const warn = `Run "${name}" for real?\n\nThis presses keys, types text and runs shell commands on this Mac right now. ` +
      "The Dry-Run switch does not apply to this button (needs Accessibility permission)." +
      (dirty ? "\n\nYou have unsaved changes: the saved version will run." : "");
    if (!confirm(warn)) return;
    try { await api.triggerWorkflow(name); setRan(name); setTimeout(() => setRan(null), 2000); }
    catch (e: any) { alert(e.message); }
  };

  if (!cfg) return <div className="tac-label text-dim p-3">loading…</div>;
  const workflows: Record<string, any> = cfg.workflows ?? {};

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base uppercase tracking-widest text-primary">Workflows</h2>
        <div className="flex items-center gap-3">
          {error && <span className="tac-label text-alert" role="alert">✕ {error}</span>}
          {saved && <span className="tac-label text-ok">✓ SAVED</span>}
          {dirty && <span className="tac-label text-warn">● UNSAVED</span>}
          <button className="btn" onClick={() => mutate((c) => { c.workflows[uniqueName("workflow", Object.keys(c.workflows), "_")] = { steps: [] }; })}>
            <Plus size={13} /> New Workflow
          </button>
          <button className="btn btn-active" onClick={save} disabled={!dirty}>
            <Save size={13} /> Save
          </button>
        </div>
      </div>

      <div className="tac-label text-dim">
        A workflow runs its steps top-to-bottom from one trigger. Bind it to any gesture / expression / voice
        command in the Binding Editor (action type → <span className="text-amber">workflow</span>), or hit Run here.
      </div>

      {Object.keys(workflows).length === 0 && (
        <div className="panel brackets flex flex-1 flex-col items-center justify-center gap-2">
          <span className="bk-bl" /><span className="bk-br" />
          <WorkflowIcon size={26} className="text-dim" />
          <span className="font-display uppercase tracking-widest text-secondary">No workflows yet</span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 overflow-auto pb-2">
        {Object.entries(workflows).map(([name, wf]) => (
          <div key={name} className="panel">
            <div className="panel-head">
              <RenameInput className="bg-transparent font-display uppercase tracking-wider text-amber focus:outline-none"
                value={name} taken={Object.keys(workflows)} aria-label="workflow name"
                onCommit={(next) => mutate((c) => { renameWorkflow(c, name, next); })} />
              <div className="flex items-center gap-2">
                {ran === name && <span className="tac-label text-ok">▶ RAN</span>}
                <button className="text-ok hover:text-primary" onClick={() => run(name)} title="Run now (real, ignores Dry-Run)" aria-label={`run ${name}`}><Play size={14} /></button>
                <button className="text-dim hover:text-alert" aria-label={`delete ${name}`} onClick={() => remove(name)}><Trash2 size={14} /></button>
              </div>
            </div>
            <div className="space-y-2 p-3">
              {(wf.steps ?? []).map((st: any, i: number) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="tac-label w-5 text-dim">{i + 1}</span>
                  <div className="flex-1"><ActionInput action={st.action} onChange={(a) => mutate((c) => { c.workflows[name].steps[i].action = a; })} /></div>
                  <input type="number" min={0} step={100} title="delay before step (ms)"
                    className="w-16 border border-hair bg-base px-1 py-1 font-mono text-micro text-secondary focus:outline-none"
                    value={st.delay_ms ?? 0}
                    onChange={(e) => mutate((c) => { c.workflows[name].steps[i].delay_ms = parseInt(e.target.value) || 0; })} />
                  <span className="tac-label text-dim">ms</span>
                  <button className="text-dim hover:text-alert" onClick={() => mutate((c) => { c.workflows[name].steps.splice(i, 1); })}><Trash2 size={13} /></button>
                </div>
              ))}
              <button className="btn w-full justify-center"
                onClick={() => mutate((c) => { c.workflows[name].steps = [...(c.workflows[name].steps ?? []), { action: { type: "key", value: "" }, delay_ms: 0 }]; })}>
                <Plus size={13} /> Add Step
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
