/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          50: "#f0f9ff",
          100: "#e0f2fe",
          200: "#bae6fd",
          300: "#7dd3fc",
          400: "#38bdf8",
          500: "#0ea5e9",
          600: "#0284c7",
          700: "#0369a1",
          800: "#075985",
          900: "#0c4a6e",
          950: "#082f49",
        },
        secondary: {
          50: "#f8fafc",
          100: "#f1f5f9",
          200: "#e2e8f0",
          300: "#cbd5e1",
          400: "#94a3b8",
          500: "#64748b",
          600: "#475569",
          700: "#334155",
          800: "#1e293b",
          900: "#0f172a",
          950: "#020617",
        },
        // Retro airport terminal palette (theme tokens via CSS variables)
        retro: {
          bg: "rgb(var(--retro-bg) / <alpha-value>)",
          panel: "rgb(var(--retro-panel) / <alpha-value>)",
          "panel-dark": "rgb(var(--retro-panel-dark) / <alpha-value>)",
          border: "rgb(var(--retro-border) / <alpha-value>)",
          ink: "rgb(var(--retro-ink) / <alpha-value>)",
          text: "rgb(var(--retro-text) / <alpha-value>)",
          "text-muted": "rgb(var(--retro-text-muted) / <alpha-value>)",
          "text-light": "rgb(var(--retro-text-light) / <alpha-value>)",
          primary: "rgb(var(--retro-primary) / <alpha-value>)",
          "primary-bright": "rgb(var(--retro-primary-bright) / <alpha-value>)",
          "primary-dark": "rgb(var(--retro-primary-dark) / <alpha-value>)",
          accent: "rgb(var(--retro-accent) / <alpha-value>)",
          success: "rgb(var(--retro-success) / <alpha-value>)",
          brass: "rgb(var(--retro-brass) / <alpha-value>)",
          led: "rgb(var(--retro-led-primary) / <alpha-value>)",
          "led-bright": "rgb(var(--retro-led-bright) / <alpha-value>)",
          forest: "rgb(var(--retro-forest) / <alpha-value>)",
          sage: "rgb(var(--retro-sage) / <alpha-value>)",
        },
      },
      fontFamily: {
        splitflap: ["DSEG14Classic", "monospace"], // Numbers only
        display: ["IBM Plex Sans", "DM Sans", "system-ui", "sans-serif"],
        mono: ["'Share Tech Mono'", "'Courier New'", "monospace"],
      },
      screens: {
        sm: "600px",
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-in-out",
        "fade-out": "fadeOut 2s ease-out forwards",
        "glow-pulse": "glowPulse 2s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(-10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        fadeOut: {
          "0%": { opacity: "1" },
          "100%": { opacity: "0" },
        },
        glowPulse: {
          "0%, 100%": { textShadow: "0 0 4px currentColor" },
          "50%": { textShadow: "0 0 12px currentColor, 0 0 20px currentColor" },
        },
      },
    },
  },
  plugins: [],
};
