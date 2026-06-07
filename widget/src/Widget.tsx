import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";
import { ChatApi } from "./api";
import { t } from "./i18n";
import type { ChatMessage, ProductResult, WidgetConfig } from "./types";

let idSeq = 0;
const nextId = () => `m${++idSeq}`;

interface Props {
  config: WidgetConfig;
}

export function Widget({ config }: Props) {
  const tr = useMemo(() => t(config.locale), [config.locale]);
  const api = useMemo(() => new ChatApi(config.apiBase), [config.apiBase]);

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [products, setProducts] = useState<ProductResult[]>([]);
  const conversationId = useRef<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Auto-scroll the transcript as content streams in.
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages, products]);

  // Move focus into the panel when it opens; close on Escape.
  useEffect(() => {
    if (!open) return;
    panelRef.current?.querySelector<HTMLElement>(".scw-input")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setProducts([]);
    const userMsg: ChatMessage = { id: nextId(), role: "user", text };
    const assistantId = nextId();
    const history = messages.map((m) => ({ role: m.role, content: m.text }));
    setMessages((prev) => [
      ...prev,
      userMsg,
      { id: assistantId, role: "assistant", text: "", pending: true },
    ]);
    setBusy(true);

    const patch = (fn: (m: ChatMessage) => ChatMessage) =>
      setMessages((prev) => prev.map((m) => (m.id === assistantId ? fn(m) : m)));

    try {
      await api.streamChat(text, history, conversationId.current, {
        onMeta: (cid) => (conversationId.current = cid),
        onToken: (tok) => patch((m) => ({ ...m, text: m.text + tok, pending: false })),
        onCitations: (c) => patch((m) => ({ ...m, citations: c })),
        onHandoff: (txt) => patch((m) => ({ ...m, text: txt, handoff: true, pending: false })),
      });
    } catch {
      patch((m) => ({ ...m, text: tr("errorGeneric"), pending: false }));
    } finally {
      patch((m) => ({ ...m, pending: false }));
      setBusy(false);
    }
  }, [api, busy, input, messages, tr]);

  const onUpload = useCallback(
    async (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      setBusy(true);
      try {
        const results = await api.visualSearch(file);
        setProducts(results);
        setMessages((prev) => [
          ...prev,
          { id: nextId(), role: "assistant", text: tr("productsFound") },
        ]);
      } catch {
        setMessages((prev) => [
          ...prev,
          { id: nextId(), role: "assistant", text: tr("errorGeneric") },
        ]);
      } finally {
        setBusy(false);
        if (fileRef.current) fileRef.current.value = "";
      }
    },
    [api, tr],
  );

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  if (!open) {
    return (
      <button class="scw-launcher" aria-label={tr("launcher")} onClick={() => setOpen(true)}>
        <span aria-hidden="true">💬</span> {tr("launcher")}
      </button>
    );
  }

  return (
    <div
      class="scw-panel"
      role="dialog"
      aria-modal="false"
      aria-label={`${config.storeName} ${tr("title")}`}
      ref={panelRef}
    >
      <div class="scw-header">
        <div>
          <h2>{config.storeName} · {tr("title")}</h2>
          <div class="scw-disclosure">{tr("disclosure")}</div>
        </div>
        <button class="scw-close" aria-label={tr("close")} onClick={() => setOpen(false)}>
          ×
        </button>
      </div>

      <div class="scw-log" ref={logRef} role="log" aria-live="polite" aria-atomic="false">
        {messages.map((m) => (
          <div key={m.id} class={`scw-msg ${m.role}${m.handoff ? " handoff" : ""}`}>
            {m.text}
            {m.citations && m.citations.length > 0 && (
              <div class="scw-sources">
                {tr("sources")}: {m.citations.join(", ")}
              </div>
            )}
          </div>
        ))}
        {products.length > 0 && (
          <div class="scw-products">
            {products.map((p) => (
              <a key={p.product_id} class="scw-product" href={p.url} target="_blank" rel="noopener">
                <b>{p.title}{p.price ? ` — $${p.price.toFixed(0)}` : ""}</b>
                <span>{p.reason}</span>
              </a>
            ))}
          </div>
        )}
        {busy && (
          <div class="scw-typing" aria-label={tr("typing")}>
            <i></i><i></i><i></i>
          </div>
        )}
      </div>

      <div class="scw-form">
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          style="display:none"
          onChange={onUpload}
          aria-hidden="true"
          tabIndex={-1}
        />
        <button
          class="scw-iconbtn"
          aria-label={tr("uploadImage")}
          title={tr("uploadImage")}
          onClick={() => fileRef.current?.click()}
        >
          📷
        </button>
        <textarea
          class="scw-input"
          rows={1}
          placeholder={tr("placeholder")}
          aria-label={tr("placeholder")}
          value={input}
          onInput={(e) => setInput((e.target as HTMLTextAreaElement).value)}
          onKeyDown={onKeyDown}
        />
        <button class="scw-sendbtn" onClick={() => void send()} disabled={busy || !input.trim()}>
          {tr("send")}
        </button>
      </div>
    </div>
  );
}
