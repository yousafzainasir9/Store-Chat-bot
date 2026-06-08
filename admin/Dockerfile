# Build the admin dashboard (React via preact/compat + Vite + Recharts) and serve
# the static bundle with nginx. Used by docker-compose's always-on `admin` service.
# The dashboard connects to the API at the URL entered on its connect screen
# (defaults to http://localhost:8000); the admin key is entered there too.

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN npm run build      # tsc --noEmit && vite build -> dist/

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# SPA: serve index.html for any path.
RUN printf 'server {\n  listen 80;\n  location / { root /usr/share/nginx/html; try_files $uri /index.html; }\n}\n' \
      > /etc/nginx/conf.d/default.conf
EXPOSE 80
