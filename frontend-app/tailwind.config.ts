import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#070b1c",
        panel: "#0e1430",
        panel2: "#121833",
        panel3: "#1a2150",
        border: "#1f2750",
        ink: "#e6ecff",
        muted: "#93a0c8",
        accent: "#5aa8ff",
        ok: "#29c48a",
        warn: "#f0b400",
        bad: "#ff5c7c",
        critical: "#ff3b5c",
        hi: "#a78bfa"
      },
      fontFamily: {
        sans: ["-apple-system", "Segoe UI", "Roboto", "Helvetica", "Arial", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "monospace"]
      }
    }
  },
  plugins: []
};
export default config;