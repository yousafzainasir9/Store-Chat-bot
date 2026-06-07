import { useEffect, useState } from "preact/hooks";
import * as Recharts from "recharts";
import type { AdminApi, Analytics } from "../api";

// recharts is typed against React; cast the namespace so its components type-check
// cleanly under Preact's JSX. Runtime is preact/compat (aliased in vite.config).
const R = Recharts as unknown as Record<string, (props: Record<string, unknown>) => JSX.Element>;

export function Overview({ api }: { api: AdminApi }) {
  const [data, setData] = useState<Analytics | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.analytics().then(setData).catch((e) => setErr(String(e)));
  }, [api]);

  if (err) return <p style="color:#dc2626">{err}</p>;
  if (!data) return <p class="muted">Loading…</p>;

  const cards: [string, string][] = [
    ["Conversations", String(data.conversations)],
    ["Deflection rate", `${(data.deflection_rate * 100).toFixed(0)}%`],
    ["Handoff rate", `${(data.handoff_rate * 100).toFixed(0)}%`],
    ["Avg confidence", data.avg_confidence.toFixed(2)],
    ["Cost / conversation", `$${data.est_cost_per_conversation_usd.toFixed(4)}`],
    ["p95 latency", `${data.p95_latency_ms.toFixed(0)} ms`],
  ];
  const fb = [
    { name: "Up", value: data.feedback_up },
    { name: "Down", value: data.feedback_down },
  ];

  return (
    <div>
      <h2>Overview</h2>
      <div class="cards">
        {cards.map(([label, value]) => (
          <div class="card" key={label}>
            <div class="label">{label}</div>
            <div class="value">{value}</div>
          </div>
        ))}
      </div>
      <div class="panel">
        <h3>Feedback</h3>
        <div style="height:220px">
          <R.ResponsiveContainer width="100%" height="100%">
            <R.BarChart data={fb}>
              <R.XAxis dataKey="name" />
              <R.YAxis allowDecimals={false} />
              <R.Tooltip />
              <R.Bar dataKey="value" fill="#1f6feb" radius={[6, 6, 0, 0]} />
            </R.BarChart>
          </R.ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
