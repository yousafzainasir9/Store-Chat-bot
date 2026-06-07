import type { WidgetConfig } from "./types";

/** Read configuration from the embedding <script> tag's data-* attributes. */
export function readConfig(): WidgetConfig {
  const el =
    (document.currentScript as HTMLScriptElement | null) ??
    document.querySelector<HTMLScriptElement>("script[data-store-name]");
  const d = el?.dataset ?? {};
  return {
    storeName: d.storeName || "our store",
    apiBase: (d.apiBase || "").replace(/\/$/, ""),
    primary: d.primary || "#1f6feb",
    position: d.position === "left" ? "left" : "right",
    locale: d.locale || (navigator.language || "en").slice(0, 2),
  };
}
