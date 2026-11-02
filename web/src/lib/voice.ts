// Browser microphone → 16 kHz PCM → energy-VAD segmentation → stream complete
// utterances to the Python /ws/voice endpoint (local faster-whisper). The
// browser handles the mic permission prompt; nothing leaves the machine.
import { useCallback, useEffect, useRef, useState } from "react";

const TARGET_RATE = 16000;
const SILENCE_MS = 600;
const MIN_SPEECH_MS = 250;
const MAX_SPEECH_MS = 12000;

export interface VoiceEntry { transcript: string; result: string; mode: string; t: number; }

export interface VoiceController {
  listening: boolean;
  ready: boolean;
  note: string | null;      // e.g. "loading the speech model (first run downloads ~150 MB)"
  mode: "command" | "dictation";
  level: number;            // 0..1 live mic level
  last: VoiceEntry | null;
  log: VoiceEntry[];
  error: string | null;
  start: (flags: { dry_run: boolean; mode: "command" | "dictation" }) => Promise<void>;
  stop: () => void;
  setMode: (m: "command" | "dictation") => void;
}

export function useVoice(): VoiceController {
  const [listening, setListening] = useState(false);
  const [ready, setReady] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [mode, setModeState] = useState<"command" | "dictation">("command");
  const [level, setLevel] = useState(0);
  const [last, setLast] = useState<VoiceEntry | null>(null);
  const [log, setLog] = useState<VoiceEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  const ctxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const nodeRef = useRef<ScriptProcessorNode | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  // VAD accumulation
  const segRef = useRef<number[]>([]);
  const inSpeechRef = useRef(false);
  const silenceRef = useRef(0);
  const thresholdRef = useRef(0.012);

  const flush = useCallback(() => {
    const seg = segRef.current;
    segRef.current = [];
    inSpeechRef.current = false;
    silenceRef.current = 0;
    const ms = (seg.length / TARGET_RATE) * 1000;
    if (ms < MIN_SPEECH_MS) return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const pcm = new Int16Array(seg.length);
    for (let i = 0; i < seg.length; i++) {
      const s = Math.max(-1, Math.min(1, seg[i]));
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    ws.send(pcm.buffer);
  }, []);

  const onAudio = useCallback((input: Float32Array, inRate: number) => {
    // downsample to 16k if needed
    let data = input;
    if (inRate !== TARGET_RATE) {
      const ratio = inRate / TARGET_RATE;
      const outLen = Math.floor(input.length / ratio);
      const out = new Float32Array(outLen);
      for (let i = 0; i < outLen; i++) out[i] = input[Math.floor(i * ratio)];
      data = out;
    }
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
    const rms = Math.sqrt(sum / data.length);
    setLevel(Math.min(1, rms * 8));

    const chunkMs = (data.length / TARGET_RATE) * 1000;
    if (rms >= thresholdRef.current) {
      inSpeechRef.current = true;
      silenceRef.current = 0;
      for (let i = 0; i < data.length; i++) segRef.current.push(data[i]);
      if ((segRef.current.length / TARGET_RATE) * 1000 >= MAX_SPEECH_MS) flush();
    } else if (inSpeechRef.current) {
      for (let i = 0; i < data.length; i++) segRef.current.push(data[i]);
      silenceRef.current += chunkMs;
      if (silenceRef.current >= SILENCE_MS) flush();
    }
  }, [flush]);

  const start = useCallback(async (flags: { dry_run: boolean; mode: "command" | "dictation" }) => {
    setError(null);
    setModeState(flags.mode);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false });
      streamRef.current = stream;
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: TARGET_RATE });
      ctxRef.current = ctx;
      const src = ctx.createMediaStreamSource(stream);
      const node = ctx.createScriptProcessor(4096, 1, 1);
      nodeRef.current = node;
      node.onaudioprocess = (e) => onAudio(e.inputBuffer.getChannelData(0), ctx.sampleRate);
      src.connect(node);
      node.connect(ctx.destination);

      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws/voice`);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;
      ws.onopen = () => { ws.send(JSON.stringify({ cmd: "config", ...flags })); setListening(true); };
      ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.error) { setError(m.error); return; }  // the server hangs up right after
        if (m.loading) { setNote(m.loading); return; }
        if (m.ready) { setReady(true); setNote(null); return; }
        if (m.transcript) {
          const entry: VoiceEntry = { transcript: m.transcript, result: m.result, mode: m.mode, t: m.t };
          setLast(entry);
          setLog((p) => [entry, ...p].slice(0, 60));
        }
      };
      ws.onclose = () => {
        // Server went away (or refused us): release the microphone.
        if (wsRef.current === ws) {
          nodeRef.current?.disconnect();
          ctxRef.current?.close().catch(() => {});
          streamRef.current?.getTracks().forEach((t) => t.stop());
          nodeRef.current = null; ctxRef.current = null; streamRef.current = null; wsRef.current = null;
          segRef.current = []; inSpeechRef.current = false; silenceRef.current = 0;
          setLevel(0);
        }
        setListening(false); setReady(false); setNote(null);
      };
    } catch (e: any) {
      setError(e?.message || "microphone access denied");
    }
  }, [onAudio]);

  const stop = useCallback(() => {
    nodeRef.current?.disconnect();
    ctxRef.current?.close().catch(() => {});
    streamRef.current?.getTracks().forEach((t) => t.stop());
    wsRef.current?.close();
    nodeRef.current = null; ctxRef.current = null; streamRef.current = null; wsRef.current = null;
    segRef.current = []; inSpeechRef.current = false; silenceRef.current = 0;
    setListening(false); setReady(false); setNote(null); setLevel(0);
  }, []);

  const setMode = useCallback((m: "command" | "dictation") => {
    setModeState(m);
    wsRef.current?.send(JSON.stringify({ cmd: "mode", mode: m }));
  }, []);

  useEffect(() => () => stop(), []);

  return { listening, ready, note, mode, level, last, log, error, start, stop, setMode };
}
