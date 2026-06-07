import { useEffect, useState } from "preact/hooks";
import type { AdminApi, ContentItem } from "../api";

export function Content({ api }: { api: AdminApi }) {
  const [items, setItems] = useState<ContentItem[]>([]);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = () =>
    api.listContent().then((r) => setItems(r.items)).catch(() => setItems([]));

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const create = async () => {
    if (!title.trim() || !body.trim()) return;
    setBusy(true);
    try {
      await api.createContent({ title, body, category: "FAQ", source: "FAQ" });
      setTitle("");
      setBody("");
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    await api.deleteContent(id);
    await refresh();
  };

  return (
    <div>
      <h2>Content & FAQs</h2>
      <div class="panel">
        <h3>New FAQ</h3>
        <p class="muted">Saving re-indexes immediately, so it's answerable right away.</p>
        <input placeholder="Question / title" value={title}
          onInput={(e) => setTitle((e.target as HTMLInputElement).value)} />
        <textarea rows={4} placeholder="Answer / body" value={body} style="margin-top:8px"
          onInput={(e) => setBody((e.target as HTMLTextAreaElement).value)} />
        <p><button class="btn" disabled={busy} onClick={() => void create()}>Add FAQ</button></p>
      </div>
      <div class="panel">
        <table>
          <thead><tr><th>Title</th><th>Category</th><th>Updated</th><th></th></tr></thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id}>
                <td>{i.title}</td>
                <td>{i.category}</td>
                <td>{new Date(i.updated_at).toLocaleString()}</td>
                <td>
                  <button class="btn danger" onClick={() => void remove(i.id)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {items.length === 0 && <p class="muted">No editable content yet.</p>}
      </div>
    </div>
  );
}
