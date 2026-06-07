// Typed admin API client. The base URL + bearer token are supplied at runtime
// (token stored in localStorage so the operator only enters it once).
export interface Analytics {
  conversations: number;
  customer_messages: number;
  assistant_messages: number;
  handoffs: number;
  handoff_rate: number;
  deflection_rate: number;
  avg_confidence: number;
  feedback_up: number;
  feedback_down: number;
  est_total_tokens: number;
  est_cost_usd: number;
  est_cost_per_conversation_usd: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
}

export interface ContentItem {
  id: string;
  title: string;
  body: string;
  category: string;
  source: string;
  locale: string;
  updated_at: string;
}

export interface ConversationSummary {
  id: string;
  created_at: string;
  message_count: number;
  handed_off: boolean;
  preview: string;
}

export interface ConversationDetail {
  id: string;
  messages: {
    id: string;
    role: string;
    content: string;
    citations: string[];
    handoff_reason: string | null;
    confidence: number;
  }[];
}

export interface ContentGap {
  suggested_title: string;
  count: number;
  examples: string[];
}

export class AdminApi {
  constructor(
    private readonly base: string,
    private readonly token: string,
  ) {}

  private async req<T>(path: string, init: RequestInit = {}): Promise<T> {
    const res = await fetch(`${this.base}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${this.token}`,
        "Content-Type": "application/json",
        ...(init.headers ?? {}),
      },
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return (await res.json()) as T;
  }

  analytics = () => this.req<Analytics>("/admin/analytics");
  listContent = () => this.req<{ items: ContentItem[] }>("/admin/content");
  createContent = (b: Partial<ContentItem>) =>
    this.req<ContentItem>("/admin/content", { method: "POST", body: JSON.stringify(b) });
  updateContent = (id: string, b: Partial<ContentItem>) =>
    this.req<ContentItem>(`/admin/content/${id}`, { method: "PATCH", body: JSON.stringify(b) });
  deleteContent = (id: string) =>
    this.req<unknown>(`/admin/content/${id}`, { method: "DELETE" });
  listConversations = () =>
    this.req<{ items: ConversationSummary[] }>("/admin/conversations");
  getConversation = (id: string) =>
    this.req<ConversationDetail>(`/admin/conversations/${id}`);
  listGaps = () => this.req<{ items: ContentGap[] }>("/admin/gaps");
  createFaqFromGap = (title: string, body: string) =>
    this.req<ContentItem>("/admin/gaps/create-faq", {
      method: "POST",
      body: JSON.stringify({ title, body }),
    });
}
