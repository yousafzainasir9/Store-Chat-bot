import { defineConfig } from "vite";

// Build a single self-contained IIFE bundle (CSS inlined) that a Shopify
// theme-app-extension can drop onto any storefront page.
export default defineConfig({
  esbuild: { jsxFactory: "h", jsxFragment: "Fragment" },
  build: {
    lib: {
      entry: "src/main.tsx",
      name: "StoreChatWidget",
      formats: ["iife"],
      fileName: () => "widget.js",
    },
    cssCodeSplit: false,
    minify: "esbuild",
    target: "es2018",
    rollupOptions: {
      output: { inlineDynamicImports: true, assetFileNames: "widget.[ext]" },
    },
  },
});
