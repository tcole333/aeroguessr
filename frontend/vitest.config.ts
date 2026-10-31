import { coverageConfigDefaults, defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// jsdom has no WebGL2, so every MapView mount logs this expected warning.
// Filtering only hides the output; console spies still see the call.
const JSDOM_NO_WEBGL2_WARNING = "[VectorBaseLayer] WebGL2 unavailable";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    onConsoleLog: (log) => !log.includes(JSDOM_NO_WEBGL2_WARNING),
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
      // The app's own code: not the generated types, the scripts or the config files.
      include: ["src/**"],
      // Keep Vitest's defaults (tests, __tests__ helpers, .d.ts) and add the MSW mocks.
      exclude: [...coverageConfigDefaults.exclude, "src/mocks/**"],
      thresholds: {
        statements: 1,
        branches: 1,
        functions: 1,
        lines: 1,
      },
    },
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "./src"),
      "@data": resolve(__dirname, "../data"),
    },
  },
});
