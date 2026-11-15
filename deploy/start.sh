#!/bin/sh
set -eu
export JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export PYTHON_ML_SERVICE_URL=http://127.0.0.1:8000
export PUBLIC_DEMO=true
export NODE_ENV=production
export PORT=7860
cd /app/TrustGuard/ml-service
python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 &
ML_PID=$!
cd /app/trustguard-platform/server
node src/index.js &
API_PID=$!
trap 'kill "$ML_PID" "$API_PID" 2>/dev/null || true' EXIT INT TERM
wait -n "$ML_PID" "$API_PID"
