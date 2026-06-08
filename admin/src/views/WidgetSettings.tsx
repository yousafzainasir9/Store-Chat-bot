import { useEffect, useState } from "preact/hooks";
import type { AdminApi, WidgetConfig } from "../api";

const POSITIONS = ["right", "left"];
const LOCALES = ["en", "es", "fr"];

export function WidgetSettings({ api, apiBase }: { api: AdminApi; apiBase: string }) {
  const [cfg, setCfg] = useState<WidgetConfig | null>(null);
  const [scriptUrl, setScriptUrl] = useState(
    localStorage.getItem("widget_script_url") || "http://localhost:8082/widget.js",
  );
  const [status, setStatus] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api.getWidgetConfig().then(setCfg).catch((e) => setStatus(String(e)));
  }, [api]);

  if (!cfg) return <p class="muted">Loading…</p>;

  const set = (patch: Partial<WidgetConfig>) => setCfg({ ...cfg, ...patch });

  const save = async () => {
    setStatus("Saving…");
    try {
      const saved = await api.updateWidgetConfig({
        store_name: cfg.store_name,
        primary_color: cfg.primary_color,
        position: cfg.position,
        locale: cfg.locale,
        greeting: cfg.greeting,
        show_image_upload: cfg.show_image_upload,
      });
      setCfg(saved);
      setStatus("Saved — embedded widgets pick this up on next load.");
    } catch (e) {
      setStatus(`Error: ${(e as Error).message}`);
    }
  };

  const snippet = `<!-- AI Support Chat widget -->
<script
  src="${scriptUrl}"
  defer
  data-api-base="${apiBase}"
  data-store-name="${cfg.store_name}"
  data-primary="${cfg.primary_color}"
  data-position="${cfg.position}"
  data-locale="${cfg.locale}"
></script>`;

  const copy = async () => {
    await navigator.clipboard.writeText(snippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div>
      <h2>Widget</h2>

      <div class="panel">
        <h3>Appearance & behavior</h3>
        <p class="muted">
          These apply to the live embedded widget on next page load (the widget
          fetches them from the backend — no need to re-paste the snippet).
        </p>

        <div class="row" style="gap:24px; flex-wrap:wrap; align-items:flex-start">
          <label style="flex:1; min-width:220px">
            Store name
            <input
              value={cfg.store_name}
              onInput={(e) => set({ store_name: (e.target as HTMLInputElement).value })}
            />
          </label>
          <label>
            Brand colour
            <input
              type="color"
              value={cfg.primary_color}
              onInput={(e) => set({ primary_color: (e.target as HTMLInputElement).value })}
              style="height:38px; padding:2px; width:64px"
            />
          </label>
        </div>

        <div class="row" style="gap:24px; flex-wrap:wrap; margin-top:12px">
          <label>
            Position
            <select
              value={cfg.position}
              onChange={(e) => set({ position: (e.target as HTMLSelectElement).value })}
            >
              {POSITIONS.map((p) => (
                <option key={p} value={p}>{p === "right" ? "Bottom right" : "Bottom left"}</option>
              ))}
            </select>
          </label>
          <label>
            Language
            <select
              value={cfg.locale}
              onChange={(e) => set({ locale: (e.target as HTMLSelectElement).value })}
            >
              {LOCALES.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </label>
          <label class="row" style="gap:8px; align-items:center; margin-top:22px">
            <input
              type="checkbox"
              checked={cfg.show_image_upload}
              onChange={(e) => set({ show_image_upload: (e.target as HTMLInputElement).checked })}
              style="width:auto"
            />
            Enable photo search (image upload)
          </label>
        </div>

        <label style="display:block; margin-top:12px">
          Greeting message (optional)
          <input
            placeholder="e.g. Hi! How can I help you today?"
            value={cfg.greeting}
            onInput={(e) => set({ greeting: (e.target as HTMLInputElement).value })}
          />
        </label>

        <p style="margin-top:14px">
          <button class="btn" onClick={() => void save()}>Save changes</button>
          {status && <span class="muted" style="margin-left:12px">{status}</span>}
        </p>
      </div>

      <div class="panel">
        <h3>Embed on your storefront</h3>
        <p class="muted">
          Paste this snippet before <code>&lt;/body&gt;</code> (or add it via the
          Shopify theme app-embed block). Set the script URL to wherever
          <code>widget.js</code> is hosted.
        </p>
        <label style="display:block; margin-bottom:10px">
          Widget script URL
          <input
            value={scriptUrl}
            onInput={(e) => {
              const v = (e.target as HTMLInputElement).value;
              setScriptUrl(v);
              localStorage.setItem("widget_script_url", v);
            }}
          />
        </label>
        <textarea
          readOnly
          rows={9}
          value={snippet}
          style="font-family:ui-monospace,monospace; font-size:13px; width:100%"
        />
        <p style="margin-top:10px">
          <button class="btn" onClick={() => void copy()}>{copied ? "Copied ✓" : "Copy snippet"}</button>
        </p>
      </div>
    </div>
  );
}
