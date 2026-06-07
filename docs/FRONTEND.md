# Frontend

Two independent frontends, both built with Vite:

- **`widget/`** — the embeddable storefront chat widget (Preact).
- **`admin/`** — the operations dashboard (React via Preact/compat).

See also [WIDGET.md](./WIDGET.md) for Shopify embedding/CSP and `widget/README.md`
/ `admin/README.md` for local dev.

## 1. Storefront widget (`widget/`)

A single self-contained bundle (`dist/widget.js`, ~24 KB raw / ~10 KB gzip, CSS
inlined) that a Shopify **theme app extension** drops onto any storefront page.
Configuration comes entirely from the embedding `<script>`'s `data-*` attributes,
so the same bundle works for any deployment.

### Files
| File | Purpose |
|---|---|
| `src/main.tsx` | Entry. Reads config, injects scoped styles once, mounts `<Widget>` into an isolated `#scw-root` appended to `<body>`. Idempotent. |
| `src/Widget.tsx` | The chat UI (Preact + hooks): launcher, panel, streaming transcript, typing indicator, image upload, product cards, citations, handoff styling, keyboard a11y. |
| `src/api.ts` | `ChatApi` — SSE chat client (parses `event:`/`data:` frames), visual-search client, widget-session token handling (`X-Widget-Token`). |
| `src/config.ts` | `readConfig()` — parses `data-*` attributes from the embedding script. |
| `src/i18n.ts` | Per-locale UI strings (en/es/fr) with English fallback. |
| `src/types.ts` | `ChatMessage`, `ProductResult`, `WidgetConfig`. |
| `src/styles.css` | Scoped (`.scw-*`), theme-variable-driven styles; mobile-first; reduced-motion support. |
| `index.html` | Dev preview page (stand-in storefront). |
| `vite.config.ts` | Builds a single IIFE bundle with inlined CSS. |

### Configuration (`data-*` attributes)
| Attribute | Purpose |
|---|---|
| `data-store-name` | Header title. |
| `data-api-base` | Backend HTTPS base URL. |
| `data-primary` | Brand colour. |
| `data-position` | `right` \| `left`. |
| `data-locale` | `en`/`es`/`fr` (falls back to browser). |

### Behavior
- Streams answers token-by-token over SSE; shows a typing indicator while busy.
- Keeps in-session history and sends prior turns as context.
- Image upload calls `/search/visual` and renders product cards.
- Shows citations under grounded answers; styles handoff messages distinctly.
- Always shows the AI-disclosure notice.
- Accessibility: dialog/log ARIA roles, `aria-live` transcript, Enter-to-send,
  Escape-to-close, visible focus rings; full-screen panel on mobile.

### Build
```bash
cd widget && npm install && npm run build      # tsc --noEmit, then vite build
cp dist/widget.js ../shopify-app/extensions/chat-widget/assets/widget.js
```

## 2. Admin dashboard (`admin/`)

A React dashboard (aliased to `preact/compat` at build for a small runtime; charts
via Recharts) that talks to the `/admin/*` API with a bearer token entered on a
connect screen and stored in `localStorage`.

### Files
| File | Purpose |
|---|---|
| `src/main.tsx` | Entry; renders `<App>` into `#app`. |
| `src/App.tsx` | Shell: connect screen (API base + admin key), sidebar nav, tab routing. |
| `src/api.ts` | `AdminApi` — typed client for analytics/content/conversations/gaps; bearer auth. |
| `src/views/Overview.tsx` | Metric cards (conversations, deflection, handoff rate, confidence, cost/conversation, p95) + feedback bar chart. |
| `src/views/Conversations.tsx` | Searchable conversation list + transcript view. |
| `src/views/Content.tsx` | Create/delete FAQs (re-indexes instantly). |
| `src/views/Gaps.tsx` | Content gaps with one-click "create FAQ". |
| `src/styles.css` | Dashboard styling. |
| `vite.config.ts` | Aliases `react`/`react-dom` → `preact/compat`. |

### Notes
- recharts is React-typed; the project type-checks against `@types/react` while
  aliasing the runtime to `preact/compat` (a standard Preact + React-library
  setup). Application code uses Preact conventions.
- The connect-screen token entry is the single seam where a production
  OAuth2/SSO login would slot in.

### Build
```bash
cd admin && npm install && npm run build       # tsc --noEmit, then vite build → dist/
```
Deploy `dist/` as a static site; lock the backend `CORS_ORIGINS` to its origin.

## 3. Shopify theme app extension (`shopify-app/`)

| File | Purpose |
|---|---|
| `extensions/chat-widget/shopify.extension.toml` | Theme app-extension manifest. |
| `extensions/chat-widget/blocks/chat_widget.liquid` | App-embed block: injects `widget.js` with merchant settings (API URL, colour, position, locale) as `data-*`. |
| `extensions/chat-widget/assets/widget.js` | The built widget bundle (copied from `widget/dist`). |
| `extensions/chat-widget/locales/en.default.json` | Extension locale. |

Deploy with the Shopify CLI (`shopify app deploy`); the merchant enables the app
embed in the theme editor and sets the API URL. See [WIDGET.md](./WIDGET.md).
