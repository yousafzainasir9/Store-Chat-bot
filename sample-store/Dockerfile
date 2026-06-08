# Sample storefront page (local demos only). Serves a mock store that embeds the
# widget from the widget asset host and points it at the local API. Both URLs are
# overridable at runtime (WIDGET_JS_URL, WIDGET_API_BASE).
FROM nginx:alpine
ENV WIDGET_JS_URL=http://localhost:8082/widget.js \
    WIDGET_API_BASE=http://localhost:8000
COPY index.html /usr/share/nginx/html/index.html.template
RUN printf '%s\n' \
      '#!/bin/sh' \
      'set -e' \
      'sed -e "s#__WIDGET_JS_URL__#${WIDGET_JS_URL}#g" -e "s#__WIDGET_API_BASE__#${WIDGET_API_BASE}#g" \' \
      '  /usr/share/nginx/html/index.html.template > /usr/share/nginx/html/index.html' \
      > /docker-entrypoint.d/40-storefront.sh \
 && chmod +x /docker-entrypoint.d/40-storefront.sh
EXPOSE 80
