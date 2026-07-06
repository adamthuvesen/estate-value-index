import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Nordic Ledger — light, Scandinavian-calm system.
        // The `tactical` namespace name is kept so existing components restyle
        // themselves; the values are now a light palette.
        tactical: {
          bg: "#FBFBFA", // Page background — warm near-white paper
          surface: "#FFFFFF", // Cards / panels
          elevated: "#F4F4F2", // Sunken insets, rails, chips
          border: "#E9E9E4", // Hairline borders
          "border-emphasis": "#D7D7D1", // Stronger borders / hover
          text: "#16171A", // Primary ink text
          muted: "#63666E", // Secondary text
          dimmed: "#767980", // Tertiary / labels — AA-legible on white (~4.4:1)
          // Interactive brand accent (links, focus, active nav) — reserved blue
          accent: "#0B62FF",
          "accent-hover": "#0A54DB",
          "accent-soft": "#4C8CFF",
          // Generic positive (kept green)
          success: "#157F4B",
          "success-dim": "#2E9D63",
          neutral: "#8A8D95",
          "neutral-hover": "#63666E",
        },
        // Diverging value scale — the only place saturated color carries meaning.
        val: {
          exc: "#157F4B", // Excellent value (deep undervalued)
          "exc-tint": "#E7F4EC",
          "exc-line": "#BFE3CD",
          great: "#2E8B57", // Great value
          good: "#4F8A6B", // Good value (muted green)
          fair: "#6B7280", // Fair value (neutral)
          "fair-tint": "#F1F2F1",
          over: "#C2681C", // Overvalued (amber/clay)
          "over-tint": "#FBF0E4",
          "over-line": "#F0D9BE",
          high: "#C0392B", // Highly overvalued (clay red)
          "high-tint": "#FBEBE9",
          "high-line": "#F1CFC9",
        },
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        chart: {
          "1": "hsl(var(--chart-1))",
          "2": "hsl(var(--chart-2))",
          "3": "hsl(var(--chart-3))",
          "4": "hsl(var(--chart-4))",
          "5": "hsl(var(--chart-5))",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "Liberation Mono", "Courier New", "monospace"],
      },
      borderRadius: {
        lg: "12px",
        md: "10px",
        sm: "8px",
        tactical: "9px", // Softened default for cards/controls
        pill: "999px",
      },
      letterSpacing: {
        tactical: "-0.01em", // Tight display tracking
        "tactical-wide": "0.08em", // Restrained label tracking (was 0.2em)
      },
      transitionTimingFunction: {
        tactical: "cubic-bezier(0.22, 0.61, 0.36, 1)", // Smooth ease-out
      },
      transitionDuration: {
        tactical: "180ms",
      },
      spacing: {
        '18': '4.5rem',
        '22': '5.5rem',
        '26': '6.5rem',
      },
      boxShadow: {
        "elev-1": "0 1px 2px rgba(16,17,20,0.04), 0 1px 3px rgba(16,17,20,0.05)",
        "elev-2": "0 4px 14px rgba(16,17,20,0.07), 0 2px 5px rgba(16,17,20,0.05)",
        "elev-3": "0 12px 32px rgba(16,17,20,0.10), 0 4px 10px rgba(16,17,20,0.06)",
        "focus": "0 0 0 3px rgba(11,98,255,0.18)",
      },
      animation: {
        "fade-in-up": "fade-in-up 0.5s cubic-bezier(0.22, 0.61, 0.36, 1) both",
        "fade-in": "fade-in 0.4s ease-out both",
        "gauge-grow": "gauge-grow 0.7s cubic-bezier(0.22, 0.61, 0.36, 1) both",
      },
      keyframes: {
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "gauge-grow": {
          "0%": { transform: "scaleX(0)" },
          "100%": { transform: "scaleX(1)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
