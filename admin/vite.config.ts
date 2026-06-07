import { defineConfig } from "vite";

// Preact-aliased React so recharts works against the small Preact runtime.
export default defineConfig({
  resolve: {
    alias: {
      react: "preact/compat",
      "react-dom": "preact/compat",
      "react/jsx-runtime": "preact/jsx-runtime",
    },
  },
  build: { target: "es2018", outDir: "dist" },
});
