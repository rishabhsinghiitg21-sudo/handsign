// REST + WebSocket client for the handsign backend.
import { useEffect, useRef, useState } from "react";

export interface Status {
  engine_running: boolean;
  mode: "idle" | "run" | "record";
  flags: { dry_run?: boolean; voice?: boolean; mouse?: boolean };
  model_present: boolean;
  gestures: string[];
  gesture_names: string[];
  builtin_gestures: string[];
  sample_counts: Record<string, number>;
  poses: string[];
  sequences: string[];
  voice_commands: string[];
  expressions: string[];
  expression_names: string[];
  workflows: Record<string, number>;
  push_to_talk: Record<string, string>;
  mouse_gesture: string;
}

export interface FireEvent {
  type: "event";
  kind: "pose" | "sequence" | "voice" | "mouse" | "error";
  name: string;
  action_type?: string;
  action_value?: string;
  mode?: string;
  detail?: string;
  dry_run?: boolean;
  t: number;
}

export interface Telemetry {
  running: boolean;
  events: FireEvent[];
  pose?: string | null;
  confidence?: number;
  hold?: number;
  stable_frames?: number;
  committed?: string | null;
  listening?: boolean;
  mode?: string | null;
  mic_rms?: number;
  sequence_progress?: string[];
  hands?: number[][][]; // [hand][21][3]
  handedness?: string[];
  frame?: string; // base64 jpeg when video enabled
  // record-mode fields
  recording?: boolean;
  capture_label?: string | null;
  capturing?: boolean;
  counts?: Record<string, number>;
  // face / expression fields
  face_present?: boolean;
  expression?: string | null;
  expression_intensity?: number;
  expr_scores?: Record<string, number>;
  face_points?: number[][]; // [n][2] normalized
  active_combo?: {
    gesture?: string | null;
    expression?: string | null;
    hands?: string[] | null;
    action_type?: string;
    action_value?: string;
  } | null;
  hand_poses?: { hand: string; pose: string | null; confidence: number }[];
}

const json = async (r: Response) => {
  if (!r.ok) {
    // FastAPI errors look like {"detail": "..."}; show that instead of just "400".
    let detail = "";
    try {
      const body = await r.json();
      detail = typeof body?.detail === "string" ? body.detail : "";
    } catch { /* not JSON */ }
    throw new Error(detail || `${r.status} ${r.statusText}`);
  }
  return r.json();
};

export const api = {
  status: (): Promise<Status> => fetch("/api/status").then(json),
  getConfig: (): Promise<any> => fetch("/api/config").then(json),
  putConfig: (cfg: any) =>
    fetch("/api/config", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(cfg),
    }).then(json),
  dataset: () => fetch("/api/dataset").then(json),
  samples: (label: string) => fetch(`/api/dataset/${encodeURIComponent(label)}/samples`).then(json),
  calibrateClassifier: () =>
    fetch("/api/calibrate/classifier", { method: "POST" }).then(json),
  startEngine: (flags: { dry_run: boolean; voice: boolean; mouse: boolean }) =>
    fetch("/api/engine/start", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(flags),
    }).then(json),
  stopEngine: () => fetch("/api/engine/stop", { method: "POST" }).then(json),
  startRecord: () => fetch("/api/record/start", { method: "POST" }).then(json),
  captureGesture: (label: string) =>
    fetch("/api/record/capture", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ label }),
    }).then(json),
  saveRecord: () => fetch("/api/record/save", { method: "POST" }).then(json),
  deleteLabel: (label: string) =>
    fetch(`/api/dataset/${encodeURIComponent(label)}`, { method: "DELETE" }).then(json),
  triggerWorkflow: (name: string) =>
    fetch(`/api/workflow/${encodeURIComponent(name)}/trigger`, { method: "POST" }).then(json),
};

/** Live telemetry over WebSocket. Auto-reconnects. Accumulates a fire-event log. */
export function useLiveSocket(video: boolean) {
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [connected, setConnected] = useState(false);
  const [log, setLog] = useState<FireEvent[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const videoRef = useRef(video);
  videoRef.current = video;

  useEffect(() => {
    let alive = true;
    let retry: ReturnType<typeof setTimeout>;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws/live`);
      wsRef.current = ws;
      ws.onopen = () => {
        setConnected(true);
        ws.send(JSON.stringify({ video: videoRef.current }));
      };
      ws.onmessage = (e) => {
        const t: Telemetry = JSON.parse(e.data);
        setTelemetry(t);
        if (t.events?.length)
          setLog((prev) => [...t.events, ...prev].slice(0, 120));
      };
      ws.onclose = () => {
        setConnected(false);
        if (alive) retry = setTimeout(connect, 1000);
      };
      ws.onerror = () => ws.close();
    };
    connect();
    return () => {
      alive = false;
      clearTimeout(retry);
      wsRef.current?.close();
    };
  }, []);

  // Push video-toggle changes to the server.
  useEffect(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN)
      wsRef.current.send(JSON.stringify({ video }));
  }, [video]);

  return { telemetry, connected, log };
}
