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
        // Tactical color system
        tactical: {
          bg: "#0a0a0a",           // Ultra-dark background
          surface: "#0f0f0f",       // Card/panel background
          elevated: "#121212",      // Elevated surfaces
          border: "#2a2a2a",        // Subtle borders
          "border-emphasis": "#404040", // Emphasized borders
          text: "#e0e0e0",          // Primary text
          muted: "#a0a0a0",         // Secondary/muted text (lightened for better contrast)
          dimmed: "#707070",        // Tertiary/placeholder text (lightened)
          accent: "#ff3333",        // Primary accent (red-orange)
          "accent-hover": "#ff4444", // Accent hover state
          "accent-soft": "#ff6666", // Softer accent for less critical actions
          success: "#00ff88",       // Success/active state (cyan-green)
          "success-dim": "#00cc6a", // Dimmed success
          neutral: "#606060",       // Neutral gray for non-critical buttons
          "neutral-hover": "#707070", // Neutral hover state
        },
        // Legacy color variables for compatibility
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
        sans: ["var(--font-inter)"],
        mono: ["var(--font-jetbrains-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "Liberation Mono", "Courier New", "monospace"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        tactical: "2px", // Minimal tactical radius
      },
      letterSpacing: {
        tactical: "0.02em", // Increased spacing for digital aesthetic
        "tactical-wide": "0.2em", // Wide spacing for labels
      },
      transitionTimingFunction: {
        tactical: "cubic-bezier(0.4, 0, 0.2, 1)", // Smooth but quick
      },
      transitionDuration: {
        tactical: "200ms", // Standard tactical transition
      },
      spacing: {
        '18': '4.5rem',   // 72px
        '22': '5.5rem',   // 88px
        '26': '6.5rem',   // 104px
      },
      animation: {
        "glow-pulse": "glow-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in-up": "fade-in-up 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        "hover-lift": "hover-lift 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
      },
      keyframes: {
        "glow-pulse": {
          "0%, 100%": {
            opacity: "1",
            boxShadow: "0 0 20px rgba(255, 51, 51, 0.3)",
          },
          "50%": {
            opacity: "0.8",
            boxShadow: "0 0 30px rgba(255, 51, 51, 0.5)",
          },
        },
        "fade-in-up": {
          "0%": {
            opacity: "0",
            transform: "translateY(10px)",
          },
          "100%": {
            opacity: "1",
            transform: "translateY(0)",
          },
        },
        "hover-lift": {
          "0%": {
            transform: "translateY(0)",
          },
          "100%": {
            transform: "translateY(-2px)",
          },
        },
      },
    },
  },
  plugins: [],
};

export default config;