FROM node:22-bookworm AS frontend
WORKDIR /build
COPY trustguard-platform/client/package*.json ./
RUN npm ci
COPY trustguard-platform/client/ ./
ENV VITE_API_URL=/api/v1 VITE_PUBLIC_DEMO=true
RUN npm run build

FROM python:3.11-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm
WORKDIR /app
COPY TrustGuard/ml-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r /tmp/requirements.txt
COPY trustguard-platform/server/package*.json ./trustguard-platform/server/
RUN cd trustguard-platform/server && npm ci --omit=dev
COPY TrustGuard/ml-service/ ./TrustGuard/ml-service/
COPY trustguard-platform/server/src/ ./trustguard-platform/server/src/
COPY --from=frontend /build/dist ./trustguard-platform/client/dist
COPY deploy/start.sh ./deploy/start.sh
RUN chmod +x /app/deploy/start.sh && useradd -m -u 1000 user && chown -R user:user /app
USER user
ENV HOME=/home/user HF_HOME=/home/user/.cache/huggingface RELOAD=false ENABLE_WEB_SEARCH_VERIFICATION=true
EXPOSE 7860
CMD ["/bin/bash", "/app/deploy/start.sh"]
