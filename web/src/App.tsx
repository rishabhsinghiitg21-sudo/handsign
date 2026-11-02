import { useEffect, useState } from "react";
import {
  Crosshair, Database, Workflow, Hand, SlidersHorizontal,
  Activity, Settings, Radio,
} from "lucide-react";
import { api, type Status } from "./lib/api";
import { useCamera } from "./lib/camera";
import { useVoice } from "./lib/voice";
import { StatusRail } from "./components/StatusRail";
import { TelemetryRail } from "./components/TelemetryRail";
import { CommandBar } from "./components/CommandBar";
import { LiveOps } from "./components/LiveOps";
import { GestureLibrary } from "./components/GestureLibrary";
import { ActionRepository } from "./components/ActionRepository";
import { BindingEditor } from "./components/BindingEditor";
import { Workflows } from "./components/Workflows";
import { Placeholder } from "./components/Placeholder";

export type ModuleId =
  | "live" | "actions" | "editor" | "gestures" | "workflows" | "telemetry" | "settings";

export const MODULES: { id: ModuleId; label: string; icon: any }[] = [
  { id: "live", label: "Live Ops", icon: Crosshair },
  { id: "actions", label: "Actions", icon: Database },
  { id: "editor", label: "Binding Editor", icon: SlidersHorizontal },
  { id: "gestures", label: "Gesture Lib", icon: Hand },
  { id: "workflows", label: "Workflows", icon: Workflow },
  { id: "telemetry", label: "Telemetry", icon: Activity },
  { id: "settings", label: "Settings", icon: Settings },
];

export default function App() {
  const [active, setActive] = useState<ModuleId>("live");
  const [status, setStatus] = useState<Status | null>(null);
  const [video, setVideo] = useState(true);
  const cam = useCamera();
  const voice = useVoice();

  const refreshStatus = () => api.status().then(setStatus).catch(() => {});
  useEffect(() => {
    refreshStatus();
    const id = setInterval(refreshStatus, 3000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-hair bg-surface/90 px-4 py-2">
        <div className="flex shrink-0 items-center gap-3 whitespace-nowrap">
          <Radio size={16} className="text-accent" />
          <span className="font-display text-base font-700 tracking-[0.25em] text-primary">HANDSIGN</span>
          <span className="tac-label">// TACTICAL CONTROL CONSOLE</span>
        </div>
        <div className="flex min-w-0 items-center gap-4 tac-label">
          <span className={`shrink-0 whitespace-nowrap ${cam.streaming ? "text-ok" : "text-dim"}`}>
            ◉ CAM {cam.streaming ? "LIVE" : "OFF"}
          </span>
          <span className={`shrink-0 whitespace-nowrap ${voice.listening ? "text-ok" : "text-dim"}`}>
            ◉ MIC {voice.listening ? "LIVE" : "OFF"}
          </span>
          {(cam.error || voice.error) && (
            <span className="min-w-0 truncate text-alert" role="alert" title={cam.error || voice.error || ""}>
              ⚠ {cam.error || voice.error}
            </span>
          )}
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[220px_1fr_300px]">
        <StatusRail active={active} onSelect={setActive} status={status} cam={cam} />
        <main className="min-h-0 overflow-auto p-3">
          {active === "live" && (
            <LiveOps cam={cam} voice={voice} status={status} video={video} onToggleVideo={() => setVideo((v) => !v)} />
          )}
          {active === "actions" && <ActionRepository />}
          {active === "editor" && <BindingEditor status={status} onChanged={refreshStatus} />}
          {active === "gestures" && (
            <GestureLibrary cam={cam} status={status} video={video} onChanged={refreshStatus} />
          )}
          {active === "workflows" && <Workflows onChanged={refreshStatus} />}
          {active === "telemetry" && <Placeholder title="Telemetry & Charts" phase="next" />}
          {active === "settings" && <Placeholder title="Settings" phase="next" />}
        </main>
        <TelemetryRail telemetry={cam.telemetry} log={cam.log} voice={voice} />
      </div>

      <CommandBar cam={cam} voice={voice} status={status} onChanged={refreshStatus} />
    </div>
  );
}
