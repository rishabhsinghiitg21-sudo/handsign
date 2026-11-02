import { useEffect, useRef } from "react";
import type { Telemetry } from "../lib/api";
import { drawHand } from "../lib/hand";

/** Live viewport: the mirrored webcam feed (browser camera) with the 21-point
 *  hand mesh + anchors drawn on top. Set `video=false` for a pure-vector look. */
export function Viewport({
  stream, telemetry, video, streaming,
}: {
  stream: MediaStream | null;
  telemetry: Telemetry | null;
  video: boolean;
  streaming: boolean;
}) {
  const videoElRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const v = videoElRef.current;
    if (v && stream && v.srcObject !== stream) {
      v.srcObject = stream;
      v.play().catch(() => {});
    }
  }, [stream]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const dpr = window.devicePixelRatio || 1;
    const w = wrap.clientWidth, h = wrap.clientHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    const ctx = canvas.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    // Crosshair + reticle only while live, so the "Camera Off" message sits on a clear backdrop.
    if (streaming) {
      ctx.strokeStyle = "rgba(56,189,248,0.20)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(w / 2, 0); ctx.lineTo(w / 2, h);
      ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2);
      ctx.stroke();
      ctx.strokeRect(w * 0.5 - 18, h * 0.5 - 18, 36, 36);
    }

    // face constellation (faint dots) + active expression tint
    const fp = telemetry?.face_points ?? [];
    if (fp.length) {
      const lit = !!telemetry?.expression;
      ctx.fillStyle = lit ? "rgba(52,211,153,0.7)" : "rgba(56,189,248,0.45)";
      for (const [x, y] of fp) {
        ctx.beginPath();
        ctx.arc(x * w, y * h, 1.3, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    const committed = !!telemetry?.committed;
    for (const pts of telemetry?.hands ?? [])
      drawHand(ctx, pts, w, h, { color: committed ? "#34D399" : "#38BDF8", lineWidth: 2 });
  }, [telemetry, streaming]);

  const noHand = streaming && !(telemetry?.hands && telemetry.hands.length);

  return (
    <div ref={wrapRef} className="brackets relative aspect-video w-full overflow-hidden border border-hair bg-base">
      <span className="bk-bl" /><span className="bk-br" />
      <video
        ref={videoElRef}
        muted playsInline
        className="absolute inset-0 h-full w-full object-cover"
        style={{ transform: "scaleX(-1)", opacity: video ? 0.75 : 0 }}
      />
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />

      <div className="absolute left-2 top-2 tac-label text-accent">
        ◰ CAM-00 {video ? "VIDEO" : "VECTOR"} {streaming ? "· LIVE" : ""}
      </div>
      {noHand && (
        <div className="absolute inset-0 flex items-center justify-center tac-label text-dim">
          ⟂ NO HAND IN FRAME
        </div>
      )}
      {!streaming && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1">
          <span className="font-display text-base uppercase tracking-widest text-secondary">Camera Off</span>
          <span className="tac-label text-dim">▶ ENGAGE FROM COMMAND BAR</span>
        </div>
      )}
    </div>
  );
}
