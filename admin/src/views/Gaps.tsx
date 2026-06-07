import { useEffect, useState } from "preact/hooks";
import type { AdminApi, ContentGap } from "../api";

export function Gaps({ api, onCreated }: { api: AdminApi; onCreated: () => void }) {
  const [items, setItems] = useState<ContentGap[]>([]);

  useEffect(() => {
    api.listGaps().then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [api]);

  const createFaq = async (gap: ContentGap) => {
    const body = window.prompt(`Answer for "${gap.suggested_title}":`, "");
    if (!body) return;
    await api.createFaqFromGap(gap.suggested_title, body);
    onCreated();
  };

  return (
    <div>
      <h2>Content gaps</h2>
      <p class="muted">
        Clusters of questions that triggered a handoff or low confidence. Turn the
        top ones into FAQs to improve coverage.
      </p>
      <div class="panel">
        <table>
          <thead><tr><th>Asked</th><th>Example questions</th><th></th></tr></thead>
          <tbody>
            {items.map((g, idx) => (
              <tr key={idx}>
                <td><b>{g.count}×</b></td>
                <td>{g.examples.join(" · ")}</td>
                <td><button class="btn" onClick={() => void createFaq(g)}>Create FAQ</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {items.length === 0 && <p class="muted">No content gaps detected. 🎉</p>}
      </div>
    </div>
  );
}
