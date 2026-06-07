import { render } from "preact";
import { readConfig } from "./config";
import { Widget } from "./Widget";
import styles from "./styles.css?inline";

/**
 * Entry point. Auto-mounts the widget into an isolated container appended to
 * <body>, injects scoped styles once, and applies the merchant's theme. Safe to
 * load multiple times (it no-ops if already mounted).
 */
function mount(): void {
  if (document.getElementById("scw-root")) return;
  const config = readConfig();

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
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}
