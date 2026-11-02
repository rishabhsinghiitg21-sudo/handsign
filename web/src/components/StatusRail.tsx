import { MODULES, type ModuleId } from "../App";
import type { Status } from "../lib/api";
import type { CameraController } from "../lib/camera";
import { Camera, Cpu, ShieldCheck, Hand } from "lucide-react";

function Stat({ ok, label, icon: Icon }: { ok: boolean; label: string; icon: any }) {
  return (
    <div className="flex items-center justify-between px-3 py-1.5">
      <span className="flex items-center gap-2 tac-label">
        <Icon size={13} className={ok ? "text-ok" : "text-dim"} />
        {label}
      </span>
      <span className={`text-micro font-mono ${ok ? "text-ok" : "text-dim"}`}>
        {ok ? "✓ OK" : "○ —"}
      </span>
    </div>
  );
}

export function StatusRail({
  active, onSelect, status, cam,
}: {
  active: ModuleId;
  onSelect: (m: ModuleId) => void;
  status: Status | null;
  cam: CameraController;
}) {
  const nGest = status?.gestures.length ?? 0;
  return (
    <nav className="flex min-h-0 flex-col border-r border-hair bg-surface/60">
      <div className="flex-1 overflow-auto py-2">
        {MODULES.map((m) => {
          const Icon = m.icon;
          return (
            <div
              key={m.id}
              className={`nav-item ${active === m.id ? "nav-item-active" : ""}`}
              onClick={() => onSelect(m.id)}
              role="button"
              tabIndex={0}
            >
              <Icon size={15} />
              {m.label}
            </div>
          );
        })}
      </div>

      <div className="border-t border-hair py-2">
        <div className="px-3 pb-1 tac-label text-dim">SYSTEM</div>
        <Stat ok={!!status?.model_present} label="Model" icon={Cpu} />
        <Stat ok={cam.streaming} label="Camera" icon={Camera} />
        <Stat ok={cam.ready} label="Recognizer" icon={Hand} />
        <Stat ok={cam.streaming} label="Engine" icon={ShieldCheck} />
        <div className="mt-2 flex items-center justify-between px-3">
          <span className="tac-label text-dim" title="Poses you recorded. The built-in poses are not counted.">RECORDED</span>
          <span className="tac-value text-label">{nGest}</span>
        </div>
      </div>
    </nav>
  );
}
