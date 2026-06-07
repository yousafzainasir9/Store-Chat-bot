# Storefront chat widget

A single, self-contained embeddable chat widget (Preact + Vite) for the Shopify
storefront. Streams grounded answers from the backend, supports image upload
(visual product search), and is brand-themeable, accessible, and multilingual.

- **Footprint:** one `dist/widget.js` (~24 KB raw / ~10 KB gzip), CSS inlined.
- **No build-time backend coupling:** the API base URL and theme come from the
  embedding `<script>`'s `data-*` attributes (set by the Shopify app-embed block).

## Develop

```bash
cd widget
npm install
npm run dev      # opens the dev preview (index.html) with a mock storefront
```

The dev page points the widget at `http://localhost:8000`; run the backend
(`uvicorn app.main:app`) alongside it.

## Build

```bash
npm run build    # type-checks, then bundles to dist/widget.js
```

Copy `dist/widget.js` into the Shopify extension assets:

```bash
cp dist/widget.js ../shopify-app/extensions/chat-widget/assets/widget.js
```

## Configuration (data-* attributes)

| Attribute          | Purpose                                    |
|--------------------|--------------------------------------------|
| `data-store-name`  | Shown in the header                        |
| `data-api-base`    | HTTPS base URL of the chatbot backend      |
| `data-primary`     | Brand colour (CSS colour)                  |
| `data-position`    | `right` or `left`                          |
| `data-locale`      | `en` / `es` / `fr` (falls back to browser) |

## Features

- Streaming responses over SSE with a typing indicator.
- Conversation history within the session; multi-turn context sent to the API.
- Image upload → visual product search, rendered as product cards.
- Citations shown under grounded answers; handoff messages styled distinctly.
- AI-disclosure notice always visible in the header.
- Accessibility: dialog/log ARIA roles, `aria-live` transcript, keyboard send
  (Enter), Escape to close, visible focus rings, reduced-motion support.
- Mobile-first: full-screen panel on small viewports.
- i18n: per-locale UI strings, extendable in `src/i18n.ts`.
- Abuse protection: requests a short-lived widget session token and sends it as
  `X-Widget-Token`; backend rate-limits per IP.
