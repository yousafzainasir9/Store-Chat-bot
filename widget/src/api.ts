import type { ProductResult, WidgetConfig } from "./types";

/** Thin client for the backend chat (SSE) and visual-search endpoints. */
export class ChatApi {
  private token: string | null = null;

  constructor(private readonly base: string) {}

  /** Fetch a short-lived widget session token (no-op if not configured). */
  async ensureSession(): Promise<void> {
    if (this.token) return;
    try {
      const res = await fetch(`${this.base}/widget/session`, { method: "POST" });
      if (res.ok) this.token = (await res.json()).token ?? null;
    } catch {
      /* token is optional; continue without it */
    }
  }

  /** Fetch merchant-managed branding/behavior so admin settings apply live. */
  async fetchServerConfig(): Promise<Partial<WidgetConfig>> {
    try {
      const res = await fetch(`${this.base}/widget/config`);
      if (!res.ok) return {};
      const d = await res.json();
      return {
        storeName: d.store_name,
        primary: d.primary_color,
        position: d.position,
        locale: d.locale,
        greeting: d.greeting,
        showImageUpload: d.show_image_upload,
      };
    } catch {
      return {};
    }
  }

  private headers(extra: Record<string, string> = {}): Record<string, string> {
    const h: Record<string, string> = { ...extra };
    if (this.token) h["X-Widget-Token"] = this.token;
    return h;
  }

  /**
   * Stream a chat answer. Invokes callbacks as Server-Sent Events arrive.
   * Returns the resolved conversation id.
   */
  async streamChat(
    message: string,
    history: { role: string; content: string }[],
    conversationId: string | null,
    cb: {
      onToken: (t: string) => void;
      onCitations: (c: string[]) => void;
      onHandoff: (text: string) => void;
      onMeta: (conversationId: string) => void;
    },
  ): Promise<void> {
    await this.ensureSession();
    const res = await fetch(`${this.base}/chat`, {
      method: "POST",
      headers: this.headers({ "Content-Type": "application/json" }),
      body: JSON.stringify({ message, history, conversation_id: conversationId }),
    });
    if (!res.ok || !res.body) throw new Error(`chat failed: ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE frames are separated by a blank line. Servers may use \r\n
      // (sse_starlette) or \n line endings, so match both.
      const frames = buffer.split(/\r\n\r\n|\n\n/);
      buffer = frames.pop() ?? "";
      for (const frame of frames) this.dispatchFrame(frame, cb);
    }
  }

  private dispatchFrame(
    frame: string,
    cb: {
      onToken: (t: string) => void;
      onCitations: (c: string[]) => void;
      onHandoff: (text: string) => void;
      onMeta: (conversationId: string) => void;
    },
  ): void {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of frame.split(/\r\n|\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      // Per the SSE spec, strip only ONE leading space after "data:".
      // Trimming fully would drop the inter-word spaces tokens carry.
      else if (line.startsWith("data:"))
        dataLines.push(line.startsWith("data: ") ? line.slice(6) : line.slice(5));
    }
    const data = dataLines.join("\n");
    if (data === "") return;
    switch (event) {
      case "token":
        cb.onToken(data);
        break;
      case "citations":
        try {
          cb.onCitations(JSON.parse(data));
        } catch {
          /* ignore malformed */
        }
        break;
      case "handoff":
        try {
          cb.onHandoff(JSON.parse(data).text ?? data);
        } catch {
          cb.onHandoff(data);
        }
        break;
      case "meta":
        try {
          cb.onMeta(JSON.parse(data).conversation_id);
        } catch {
          /* ignore */
        }
        break;
    }
  }

  /** Visual product search from an uploaded image. */
  async visualSearch(file: File): Promise<ProductResult[]> {
    await this.ensureSession();
    const form = new FormData();
    form.append("image", file);
    const res = await fetch(`${this.base}/search/visual`, {
      method: "POST",
      headers: this.headers(),
      body: form,
    });
    if (!res.ok) throw new Error(`visual search failed: ${res.status}`);
    return (await res.json()).results ?? [];
  }
}
