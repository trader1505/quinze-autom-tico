#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="${REPO_URL:-https://github.com/trader1505/quinze-autom-tico.git}"
BRANCH="${BRANCH:-cursor/laps1505-bot-binance-5cc7}"
APP_DIR="${APP_DIR:-/opt/laps1505}"
LEGACY_DIR="${LEGACY_DIR:-$HOME/quinze-autom-tico}"
BOT_PORT="${BOT_PORT:-8080}"

log() {
  printf '[LAPS1505-NUKE] %s\n' "$*"
}

require_root() {
  if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    log "Execute como root: sudo bash scripts/nuke_and_reinstall_live.sh"
    exit 1
  fi
}

install_docker_if_needed() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    return
  fi
  log "Instalando Docker + Compose..."
  apt-get update
  apt-get install -y ca-certificates curl gnupg git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" >/etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

read_secret() {
  local prompt="$1"
  local var_name="$2"
  local value=""
  while [ -z "${value}" ]; do
    read -r -s -p "${prompt}" value
    printf '\n'
    if [ -z "${value}" ]; then
      log "Valor nao pode ficar vazio."
    fi
  done
  printf -v "${var_name}" '%s' "${value}"
}

read_env_key() {
  local file_path="$1"
  local key="$2"
  if [ ! -f "${file_path}" ]; then
    return 1
  fi
  local value
  value="$(awk -F= -v k="${key}" '$1==k{print substr($0, index($0, "=")+1); exit}' "${file_path}" 2>/dev/null || true)"
  if [ -n "${value}" ]; then
    printf '%s' "${value}"
    return 0
  fi
  return 1
}

cleanup_old_runtime() {
  # Prevent deleting the shell's current working directory.
  cd /

  log "Parando servicos e containers antigos..."
  systemctl stop nginx laps-bot-api laps-bot laps-crypto-dashboard laps-crypto 2>/dev/null || true
  docker ps --filter "publish=${BOT_PORT}" -q | xargs -r docker rm -f
  fuser -k "${BOT_PORT}/tcp" 2>/dev/null || true

  docker rm -f laps1505-bot 2>/dev/null || true
  docker network rm laps1505_default 2>/dev/null || true

  log "Apagando pastas antigas..."
  rm -rf "${APP_DIR}"
  rm -rf "${LEGACY_DIR}"
}

fresh_clone() {
  log "Clonando repositorio limpo em ${APP_DIR}..."
  mkdir -p "$(dirname "${APP_DIR}")"
  git clone "${REPO_URL}" "${APP_DIR}"
  git -C "${APP_DIR}" checkout "${BRANCH}"
}

write_env() {
  local api_key="$1"
  local api_secret="$2"
  cat > "${APP_DIR}/.env" <<EOF
BOT_SYMBOL=DOGEUSDT
BOT_TRADING_SYMBOLS=DOGEUSDT,XRPUSDT,ADAUSDT,TRXUSDT,SOLUSDT,POLUSDT,LINKUSDT,AVAXUSDT,DOTUSDT,LTCUSDT,ATOMUSDT,NEARUSDT,ARBUSDT,OPUSDT,APTUSDT,SUIUSDT,INJUSDT,SEIUSDT,1000PEPEUSDT,WIFUSDT,1000BONKUSDT,1000FLOKIUSDT,1000SHIBUSDT,FILUSDT,ETCUSDT,AAVEUSDT,UNIUSDT,RUNEUSDT,ALGOUSDT,HBARUSDT
BOT_INTERVAL=15m
BOT_EMA_SHORT=12
BOT_EMA_LONG=26
BOT_ENTRY_FRACTION=0.01
BOT_MIN_NOTIONAL=5.0
BOT_MAX_NOTIONAL_PER_OP=5.0
BOT_ORDER_SLICES=1
BOT_MAX_CONCURRENT_OPS=30
BOT_SPOT_TARGET=0.80
BOT_FUTURES_TARGET=0.20
BOT_TP_ROI=1.0
BOT_RECOVERY_MULTIPLIER=3.0
BOT_MARGIN_STRESS=0.60
BOT_MARGIN_RECOVERY=0.30
BOT_POLL_SECONDS=5
BOT_DRY_RUN=false
BOT_API_HOST=0.0.0.0
BOT_API_PORT=${BOT_PORT}
BINANCE_API_KEY=${api_key}
BINANCE_API_SECRET=${api_secret}
EOF
  chmod 600 "${APP_DIR}/.env"
}

start_fresh_stack() {
  log "Subindo stack limpa..."
  docker compose -f "${APP_DIR}/docker-compose.yml" --env-file "${APP_DIR}/.env" up -d --build
}

wait_and_boot_engine() {
  log "Aguardando API..."
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:${BOT_PORT}/api/status" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done

  curl -fsS -X POST "http://127.0.0.1:${BOT_PORT}/api/start" >/dev/null
  for _ in $(seq 1 4); do
    curl -fsS -X POST "http://127.0.0.1:${BOT_PORT}/api/cycle" >/dev/null || true
    sleep 2
  done
}

main() {
  require_root
  install_docker_if_needed

  BINANCE_API_KEY="${BINANCE_API_KEY:-}"
  BINANCE_API_SECRET="${BINANCE_API_SECRET:-}"

  if [ -z "${BINANCE_API_KEY}" ]; then
    BINANCE_API_KEY="$(read_env_key "${APP_DIR}/.env" "BINANCE_API_KEY" || true)"
  fi
  if [ -z "${BINANCE_API_KEY}" ]; then
    BINANCE_API_KEY="$(read_env_key "${LEGACY_DIR}/.env" "BINANCE_API_KEY" || true)"
  fi
  if [ -z "${BINANCE_API_SECRET}" ]; then
    BINANCE_API_SECRET="$(read_env_key "${APP_DIR}/.env" "BINANCE_API_SECRET" || true)"
  fi
  if [ -z "${BINANCE_API_SECRET}" ]; then
    BINANCE_API_SECRET="$(read_env_key "${LEGACY_DIR}/.env" "BINANCE_API_SECRET" || true)"
  fi

  if [ -z "${BINANCE_API_KEY}" ]; then
    read_secret "Digite BINANCE_API_KEY (oculto): " BINANCE_API_KEY
  fi
  if [ -z "${BINANCE_API_SECRET}" ]; then
    read_secret "Digite BINANCE_API_SECRET (oculto): " BINANCE_API_SECRET
  fi

  cleanup_old_runtime
  fresh_clone
  write_env "${BINANCE_API_KEY}" "${BINANCE_API_SECRET}"
  start_fresh_stack
  wait_and_boot_engine
  log "Instalacao limpa concluida."
  log "Painel: http://$(hostname -I | awk '{print $1}'):${BOT_PORT}/?v=$(date +%s)"
  curl -fsS "http://127.0.0.1:${BOT_PORT}/api/status"
  printf '\n'
}

main "$@"
