import { render } from "preact";
import { ChatApi } from "./api";
import { readConfig } from "./config";
import { Widget } from "./Widget";
import type { WidgetConfig } from "./types";
import styles from "./styles.css?inline";

/**
 * Entry point. Reads data-* defaults from the embedding script, then fetches the
 * merchant-managed config from the backend (admin settings) and applies it on top,
 * so branding/behavior can be changed in the admin without editing the embed.
 */
async function mount(): Promise<void> {
  if (document.getElementById("scw-root")) return;
  const base = readConfig();
  const server = await new ChatApi(base.apiBase).fetchServerConfig();
  const config: WidgetConfig = { ...base, ...server };

  const styleEl = document.createElement("style");
  styleEl.textContent = styles;
  document.head.appendChild(styleEl);

  const root = document.createElement("div");
  root.id = "scw-root";
  root.className = `scw-root scw-${config.position}`;
  root.style.setProperty("--scw-primary", config.primary);
  document.body.appendChild(root);

  render(<Widget config={config} />, root);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => void mount());
} else {
  void mount();
}
