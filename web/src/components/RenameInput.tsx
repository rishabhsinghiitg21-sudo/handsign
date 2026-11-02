import { useEffect, useState } from "react";

/** Text field for a name that is also an object key. Edits stay local and are
 *  committed on blur / Enter, so the row isn't rebuilt (and focus lost) on every
 *  keystroke. An empty or already-used name is reverted. */
export function RenameInput({
  value, taken, onCommit, className = "", ...rest
}: {
  value: string;
  taken: string[];
  onCommit: (next: string) => void;
  className?: string;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);

  const commit = () => {
    const next = draft.trim();
    if (!next || (next !== value && taken.includes(next))) { setDraft(value); return; }
    if (next !== value) onCommit(next);
    else setDraft(value);
  };
  return (
    <input
      {...rest}
      className={className}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") { setDraft(value); (e.target as HTMLInputElement).blur(); }
      }}
    />
  );
}
