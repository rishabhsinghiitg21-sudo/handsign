// Shared action editor: type selector + value (or workflow dropdown).
const ACTION_TYPES = ["key", "text", "shell", "mouse", "workflow"];

export function ActionInput({
  action, onChange, workflowNames = [],
}: {
  action: any;
  onChange: (a: any) => void;
  workflowNames?: string[];
}) {
  const a = action ?? { type: "key", value: "" };
  return (
    <div className="flex items-center gap-1">
      <select
        className="border border-hair bg-base px-1 py-1 font-mono text-micro text-accent focus:outline-none"
        value={a.type}
        onChange={(e) => onChange({ ...a, type: e.target.value })}
      >
        {ACTION_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
      {a.type === "workflow" ? (
        <select
          className="min-w-0 flex-1 border border-hair bg-base px-2 py-1 font-mono text-micro text-amber focus:border-accent focus:outline-none"
          value={a.value}
          onChange={(e) => onChange({ ...a, value: e.target.value })}
        >
          <option value="">choose workflow…</option>
          {workflowNames.map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      ) : (
        <input
          className="min-w-0 flex-1 border border-hair bg-base px-2 py-1 font-mono text-micro text-primary focus:border-accent focus:outline-none"
          value={a.value}
          placeholder={a.type === "key" ? "cmd+enter" : a.type === "shell" ? "open -a Terminal" : "value"}
          onChange={(e) => onChange({ ...a, value: e.target.value })}
        />
      )}
    </div>
  );
}
