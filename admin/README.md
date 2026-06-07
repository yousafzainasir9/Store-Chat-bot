# Admin dashboard

A React (Preact/compat) + Vite dashboard for operating the support chatbot:
analytics, conversation review, content/FAQ management, and the feedback→content
gap loop. It talks to the backend `/admin/*` API with a bearer token.

## Develop

```bash
cd admin
npm install
npm run dev      # http://localhost:5173
```

On first load, enter the **API base URL** (e.g. `http://localhost:8000`) and the
**Admin API key** (`ADMIN_API_KEY` on the backend). Both are stored in
`localStorage` so you only enter them once.

## Build

```bash
npm run build    # type-checks (tsc) then bundles with Vite -> dist/
```

Deploy `dist/` as a static site (any static host or behind the same domain as
the API). Lock the backend `CORS_ORIGINS` to the dashboard's origin.

## Views

- **Overview** — conversations, deflection vs. handoff rate, average confidence,
  estimated cost per conversation, p95 latency, and a feedback chart.
- **Conversations** — searchable list + full transcript with handoff reasons.
- **Content & FAQs** — create/delete editable FAQs; saving re-indexes instantly,
  so the new answer is live immediately.
- **Content gaps** — clustered questions that triggered handoff/low confidence;
  one click turns a gap into an indexed FAQ.

## Notes

- recharts is React-typed; the build aliases `react`/`react-dom` to
  `preact/compat` (see `vite.config.ts`) and type-checks against `@types/react`,
  while the rest of the app uses Preact directly.
- A full OAuth2/SSO login slots in front of the token entry for production.
