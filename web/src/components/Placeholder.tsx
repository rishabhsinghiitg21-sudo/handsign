import { Construction } from "lucide-react";

export function Placeholder({ title, phase }: { title: string; phase: string }) {
  return (
    <div className="flex h-full flex-col">
      <h2 className="mb-3 font-display text-base uppercase tracking-widest text-primary">
        {title}
      </h2>
      <div className="panel brackets flex flex-1 flex-col items-center justify-center gap-2">
        <span className="bk-bl" />
        <span className="bk-br" />
        <Construction size={28} className="text-dim" />
        <span className="font-display uppercase tracking-widest text-secondary">
          Module Offline
        </span>
        <span className="tac-label text-dim">SCHEDULED · {phase}</span>
      </div>
    </div>
  );
}
