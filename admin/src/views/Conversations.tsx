import { useEffect, useState } from "preact/hooks";
import type { AdminApi, ConversationDetail, ConversationSummary } from "../api";

export function Conversations({ api }: { api: AdminApi }) {
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [active, setActive] = useState<ConversationDetail | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    api.listConversations().then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [api]);

  const open = (id: string) => {
    api.getConversation(id).then(setActive).catch(() => setActive(null));
  };

  const shown = items.filter((c) => c.preview.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div>
      <h2>Conversations</h2>
      <div class="panel">
        <input
          placeholder="Search transcripts…"
          value={filter}
          onInput={(e) => setFilter((e.target as HTMLInputElement).value)}
        />
      </div>
      <div class="panel">
        <table>
          <thead>
            <tr><th>When</th><th>Messages</th><th>Status</th><th>Preview</th></tr>
          </thead>
          <tbody>
            {shown.map((c) => (
              <tr key={c.id} style="cursor:pointer" onClick={() => open(c.id)}>
                <td>{new Date(c.created_at).toLocaleString()}</td>
                <td>{c.message_count}</td>
                <td>
                  <span class={`badge ${c.handed_off ? "handoff" : "ok"}`}>
                    {c.handed_off ? "Handoff" : "Resolved"}
                  </span>
                </td>
                <td>{c.preview}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length === 0 && <p class="muted">No conversations yet.</p>}
      </div>
      {active && (
        <div class="panel transcript">
          <h3>Transcript</h3>
          {active.messages.map((m) => (
            <div key={m.id} class={`msg ${m.role}`}>
              <b>{m.role}:</b> {m.content}
              {m.handoff_reason && <span class="badge handoff"> {m.handoff_reason}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
