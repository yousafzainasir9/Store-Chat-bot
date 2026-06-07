# Embedding the chat widget on Shopify

The widget ships as a **theme app extension** (`shopify-app/extensions/chat-widget`)
with an **app embed block**. The merchant enables it from the theme editor — no
theme code changes required.

## Deploy steps

1. **Build the widget** and copy the asset into the extension:
   ```bash
   cd widget && npm install && npm run build
   cp dist/widget.js ../shopify-app/extensions/chat-widget/assets/widget.js
   ```
2. **Push the extension** with the Shopify CLI from `shopify-app/`:
   ```bash
   shopify app deploy
   ```
3. In the Shopify admin: **Online Store → Themes → Customize → App embeds**,
   enable **AI Support Chat**, then set the **API base URL** (your deployed
   backend), brand colour, position, and optional language.

## CORS

The backend must allow the storefront origin. Set `CORS_ORIGINS` to the exact
storefront origin(s) in production (e.g. `https://acme-threads.myshopify.com,
https://www.acmethreads.com`) — do not ship `*`.

## Content-Security-Policy

If the storefront theme sets a CSP, allow the widget to load and call the API:

```
script-src 'self' https://cdn.shopify.com;
connect-src 'self' https://your-chatbot-api.example.com;
img-src 'self' https://your-cdn.example.com data:;
style-src 'self' 'unsafe-inline';
```

The widget injects one scoped `<style>` (hence `'unsafe-inline'` for styles, or
supply a nonce). It only connects to the configured `data-api-base`.

## Abuse protection

- The widget calls `POST /widget/session` for a short-lived signed token and
  sends it as `X-Widget-Token`. Enforce it by setting `WIDGET_SECRET` and
  `WIDGET_REQUIRE_TOKEN=true`.
- The backend rate-limits `/chat` and `/search/visual` per IP
  (`RATE_LIMIT_PER_MINUTE`). At multi-instance scale, back the limiter with Redis.
- Security headers are added to every response (`SECURITY_HEADERS_ENABLED`).
