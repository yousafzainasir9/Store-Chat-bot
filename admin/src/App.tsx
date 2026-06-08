import { useCallback, useEffect, useState } from "preact/hooks";
import { AdminApi } from "./api";
import { Overview } from "./views/Overview";
import { Conversations } from "./views/Conversations";
import { Content } from "./views/Content";
import { Gaps } from "./views/Gaps";
import { WidgetSettings } from "./views/WidgetSettings";

type Tab = "overview" | "conversations" | "content" | "gaps" | "widget";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "conversations", label: "Conversations" },
  { id: "content", label: "Content & FAQs" },
  { id: "gaps", label: "Content gaps" },
  { id: "widget", label: "Widget" },
];

export function App() {
  const [base, setBase] = useState(localStorage.getItem("admin_base") || "http://localhost:8000");
  const [token, setToken] = useState(localStorage.getItem("admin_token") || "");
  const [authed, setAuthed] = useState(false);
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState("");

  const api = new AdminApi(base, token);

  const connect = useCallback(async () => {
    setError("");
    try {
      await new AdminApi(base, token).analytics();
      localStorage.setItem("admin_base", base);
      localStorage.setItem("admin_token", token);
      setAuthed(true);
    } catch (e) {
      setError(`Could not connect: ${(e as Error).message}`);
    }
  }, [base, token]);

  useEffect(() => {
    if (token) void connect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!authed) {
    return (
      <div class="login panel">
        <h1>Support Chatbot — Admin</h1>
        <p class="muted">Connect to your chatbot backend.</p>
        <label>API base URL</label>
        <input value={base} onInput={(e) => setBase((e.target as HTMLInputElement).value)} />
        <label>Admin API key</label>
        <input
          type="password"
          value={token}
          onInput={(e) => setToken((e.target as HTMLInputElement).value)}
        />
        {error && <p style="color:#dc2626">{error}</p>}
        <p>
          <button class="btn" onClick={() => void connect()}>Connect</button>
        </p>
      </div>
    );
  }

  return (
    <div class="app">
      <aside class="sidebar">
        <h1>Support Admin</h1>
        <nav class="nav">
          {TABS.map((t) => (
            <button key={t.id} class={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </nav>
      </aside>
      <main class="main">
        {tab === "overview" && <Overview api={api} />}
        {tab === "conversations" && <Conversations api={api} />}
        {tab === "content" && <Content api={api} />}
        {tab === "gaps" && <Gaps api={api} onCreated={() => setTab("content")} />}
        {tab === "widget" && <WidgetSettings api={api} apiBase={base} />}
      </main>
    </div>
  );
}
