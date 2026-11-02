import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { centerForPreview, drawHand } from "../lib/hand";

const cache = new Map<string, number[][]>(); // label -> centered medoid (21×3)

async function loadMedoid(label: string): Promise<number[][] | null> {
  if (cache.has(label)) return cache.get(label)!;
  try {
    const s = await api.samples(label);
    if (!s.medoid) return null; // built-in pose: nothing recorded yet
    const centered = centerForPreview(s.medoid as number[][]);
    cache.set(label, centered);
    return centered;
  } catch {
    return null;
  }
}

/** Animated dummy-hand preview. Pass one label (single pose) or several
 *  (a sequence) — it steps through them on a loop. */
export function GesturePreview({
  labels, size = 120, color = "#38BDF8",
}: {
  labels: string[];
  size?: number;
  color?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const framesRef = useRef<(number[][] | null)[]>([]);
  const [ready, setReady] = useState(false);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let alive = true;
    Promise.all(labels.map(loadMedoid)).then((res) => {
      if (!alive) return;
      framesRef.current = res;
      setMissing(res.every((r) => r === null));
      setReady(true);
    });
    return () => { alive = false; };
  }, [labels.join("|")]);

  useEffect(() => {
    if (!ready) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    const ctx = canvas.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    let raf = 0;
    let start = performance.now();
    const frames = framesRef.current.filter(Boolean) as number[][][];
    const STEP = 900; // ms per pose

    const lerp = (a: number[][], b: number[][], t: number) =>
      a.map((p, i) => [p[0] + (b[i][0] - p[0]) * t, p[1] + (b[i][1] - p[1]) * t]);

    const tick = (now: number) => {
      ctx.clearRect(0, 0, size, size);
      // subtle frame
      ctx.strokeStyle = "rgba(56,189,248,0.15)";
      ctx.strokeRect(0.5, 0.5, size - 1, size - 1);

      if (frames.length) {
        let pose: number[][];
        if (frames.length === 1) {
          const bob = 0.005 * Math.sin((now - start) / 500);
          pose = frames[0].map(([x, y]) => [x, y + bob]);
        } else {
          const elapsed = (now - start) / STEP;
          const i = Math.floor(elapsed) % frames.length;
          const j = (i + 1) % frames.length;
          const t = elapsed - Math.floor(elapsed);
          const tt = t < 0.7 ? 0 : (t - 0.7) / 0.3; // hold then quick transition
          pose = lerp(frames[i], frames[j], tt);
        }
        drawHand(ctx, pose, size, size, { color, lineWidth: 1.5, glow: true });
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [ready, size, color]);

  if (missing)
    return (
      <div
        className="flex items-center justify-center border border-hair bg-base tac-label text-dim"
        style={{ width: size, height: size }}
      >
        NO PREVIEW
      </div>
    );

  return (
    <canvas
      ref={canvasRef}
      className="border border-hair bg-base"
      style={{ width: size, height: size }}
      aria-label={`preview of ${labels.join(" then ")}`}
    />
  );
}
