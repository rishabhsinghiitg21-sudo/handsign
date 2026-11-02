/** Tactical command-console theme — ice tactical blue accent.
 *  Dark, rectilinear, hairline borders, monospace telemetry.
 *  All foreground/background pairs target >=4.5:1 (WCAG AA). */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "#0A0E12",
        surface: "#11161C",
        elevated: "#161D24",
        hair: "#243038",
        live: "#33414B",
        primary: "#D6DEE6", // text-primary  (~13:1 on base)
        secondary: "#8A97A3", // text-secondary (~5:1)
        dim: "#5C6873", // non-essential only (~3:1)
        accent: "#38BDF8", // ICE TACTICAL BLUE
        "accent-dim": "#1E4E63",
        ok: "#34D399",
        warn: "#FBBF24",
        alert: "#F87171",
        amber: "#F5A623", // secondary data series (distinct from blue accent)
      },
      fontFamily: {
        display: ['Oxanium', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        micro: ["11px", { lineHeight: "1.3", letterSpacing: "0.04em" }],
        label: ["12px", { lineHeight: "1.4", letterSpacing: "0.03em" }],
        data: ["13px", { lineHeight: "1.5" }],
        base: ["14px", { lineHeight: "1.5" }],
      },
      borderRadius: { DEFAULT: "2px", sm: "1px" },
      boxShadow: {
        glow: "0 0 0 1px #38BDF8, 0 0 16px -6px #38BDF8",
        "glow-ok": "0 0 0 1px #34D399, 0 0 16px -6px #34D399",
      },
      keyframes: {
        pulse2: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.35" } },
        sweep: { "0%": { transform: "translateY(-100%)" }, "100%": { transform: "translateY(100%)" } },
      },
      animation: {
        pulse2: "pulse2 1.1s ease-in-out infinite",
        sweep: "sweep 4s linear infinite",
      },
    },
  },
  plugins: [],
};
