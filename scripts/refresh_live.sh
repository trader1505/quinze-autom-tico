#!/usr/bin/env bash
set -Eeuo pipefail

BRANCH="${BRANCH:-cursor/laps1505-bot-binance-5cc7}"
APP_DIR="${APP_DIR:-/opt/laps1505}"

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "Execute como root: sudo bash scripts/refresh_live.sh"
  exit 1
fi

if [ ! -d "${APP_DIR}/.git" ]; then
  echo "Repositorio nao encontrado em ${APP_DIR}"
  exit 1
fi

cd "${APP_DIR}"
git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git reset --hard "origin/${BRANCH}"

if [ ! -f .env ]; then
  echo ".env nao encontrado em ${APP_DIR}"
  exit 1
fi

API_KEY="$(grep -m1 '^BINANCE_API_KEY=' .env | cut -d= -f2- || true)"
API_SECRET="$(grep -m1 '^BINANCE_API_SECRET=' .env | cut -d= -f2- || true)"
if [ -z "${API_KEY}" ] || [ -z "${API_SECRET}" ]; then
  echo "BINANCE_API_KEY/BINANCE_API_SECRET nao configurados na .env"
  exit 1
fi

upsert_env() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    echo "${key}=${value}" >> .env
  fi
}

upsert_env BOT_DRY_RUN false
upsert_env BOT_SYMBOL DOGEUSDT
upsert_env BOT_TRADING_SYMBOLS DOGEUSDT,XRPUSDT,ADAUSDT,TRXUSDT,SOLUSDT,POLUSDT,LINKUSDT,AVAXUSDT,DOTUSDT,LTCUSDT,ATOMUSDT,NEARUSDT,ARBUSDT,OPUSDT,APTUSDT,SUIUSDT,INJUSDT,SEIUSDT,1000PEPEUSDT,WIFUSDT,1000BONKUSDT,1000FLOKIUSDT,1000SHIBUSDT,FILUSDT,ETCUSDT,AAVEUSDT,UNIUSDT,RUNEUSDT,ALGOUSDT,HBARUSDT
upsert_env BOT_INTERVAL 15m
upsert_env BOT_EMA_SHORT 12
upsert_env BOT_EMA_LONG 26
upsert_env BOT_ENTRY_FRACTION 0.01
upsert_env BOT_MIN_NOTIONAL 5.0
upsert_env BOT_MAX_NOTIONAL_PER_OP 5.0
upsert_env BOT_ORDER_SLICES 1
upsert_env BOT_MAX_CONCURRENT_OPS 30
upsert_env BOT_POLL_SECONDS 5
upsert_env BOT_API_HOST 0.0.0.0
upsert_env BOT_API_PORT 8080
upsert_env BINANCE_API_KEY "${API_KEY}"
upsert_env BINANCE_API_SECRET "${API_SECRET}"
chmod 600 .env

systemctl stop nginx laps-bot-api laps-bot laps-crypto-dashboard laps-crypto 2>/dev/null || true
docker ps --filter publish=8080 -q | xargs -r docker rm -f
fuser -k 8080/tcp 2>/dev/null || true

docker compose down --remove-orphans || true
docker compose up -d --build

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8080/api/status >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

curl -fsS -X POST http://127.0.0.1:8080/api/start >/dev/null
for _ in $(seq 1 4); do
  curl -fsS -X POST http://127.0.0.1:8080/api/cycle >/dev/null || true
  sleep 2
done

echo "HEAD $(git rev-parse --short HEAD)"
curl -fsS http://127.0.0.1:8080/api/status
echo
echo "PAINEL: http://$(hostname -I | awk '{print $1}'):8080/?v=$(date +%s)"
