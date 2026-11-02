// MediaPipe hand topology + a canvas renderer for the 21-point mesh.

export const HAND_CONNECTIONS: [number, number][] = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [0, 5], [5, 6], [6, 7], [7, 8],
  [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16],
  [13, 17], [17, 18], [18, 19], [19, 20],
  [0, 17],
];

const FINGERTIPS = new Set([4, 8, 12, 16, 20]);

export interface DrawOpts {
  color?: string;
  anchorColor?: string;
  lineWidth?: number;
  /** landmarks are normalized [0..1] (image space) when true, else already in px */
  normalized?: boolean;
  glow?: boolean;
}

/** Draw a 21-point hand mesh onto a 2D context sized w×h. */
export function drawHand(
  ctx: CanvasRenderingContext2D,
  pts: number[][],
  w: number,
  h: number,
  opts: DrawOpts = {}
) {
  const {
    color = "#38BDF8",
    anchorColor = "#D6DEE6",
    lineWidth = 1.5,
    normalized = true,
    glow = true,
  } = opts;
  const P = pts.map(([x, y]) => [normalized ? x * w : x, normalized ? y * h : y]);

  ctx.save();
  if (glow) {
    ctx.shadowColor = color;
    ctx.shadowBlur = 8;
  }
  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;
  ctx.lineCap = "round";
  for (const [a, b] of HAND_CONNECTIONS) {
    ctx.beginPath();
    ctx.moveTo(P[a][0], P[a][1]);
    ctx.lineTo(P[b][0], P[b][1]);
    ctx.stroke();
  }
  ctx.shadowBlur = 0;
  for (let i = 0; i < P.length; i++) {
    const tip = FINGERTIPS.has(i);
    ctx.beginPath();
    ctx.fillStyle = tip ? color : anchorColor;
    ctx.arc(P[i][0], P[i][1], tip ? 4 : 2.5, 0, Math.PI * 2);
    ctx.fill();
    if (i === 0) {
      // wrist reticle
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(P[i][0], P[i][1], 9, 0, Math.PI * 2);
      ctx.stroke();
    }
  }
  ctx.restore();
}

/** Map wrist-relative normalized features (21×3, centered at origin) into a
 *  centered, scaled layout for the dummy-hand preview canvases. */
export function centerForPreview(pts: number[][]): number[][] {
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const span = Math.max(maxX - minX, maxY - minY) || 1;
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
  // normalize into [0.2..0.8] box, y-down
  return pts.map(([x, y]) => [
    0.5 + ((x - cx) / span) * 0.6,
    0.5 + ((y - cy) / span) * 0.6,
  ]);
}
