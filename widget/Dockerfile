# Build the embeddable widget and serve the widget.js asset (an "asset host"
# like Shopify's CDN). The sample storefront and real storefronts load it from
# here. Used by docker-compose's always-on `widget` service.

# ---- Build the widget bundle with Vite ----
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY tsconfig.json vite.config.ts ./
COPY src ./src
RUN npm run build      # tsc --noEmit && vite build -> dist/widget.js

# ---- Serve the asset with nginx (permissive CORS so any storefront can load it) ----
FROM nginx:alpine
# Drop nginx's stock welcome page, then publish our asset + a small landing page.
RUN rm -f /usr/share/nginx/html/index.html
COPY --from=build /app/dist/widget.js /usr/share/nginx/html/widget.js
COPY landing.html /usr/share/nginx/html/index.html
RUN printf 'server {\n  listen 80;\n  add_header Access-Control-Allow-Origin *;\n  location / { root /usr/share/nginx/html; try_files $uri $uri/ /index.html; }\n}\n' \
      > /etc/nginx/conf.d/default.conf
EXPOSE 80
