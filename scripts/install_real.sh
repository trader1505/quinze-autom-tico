#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="${REPO_URL:-https://github.com/trader1505/quinze-autom-tico.git}"
REPO_BRANCH="${REPO_BRANCH:-cursor/laps1505-bot-binance-5cc7}"
INSTALL_DIR="${INSTALL_DIR:-/opt/laps1505}"
BOT_PORT="${BOT_PORT:-8080}"
BOT_SYMBOL="${BOT_SYMBOL:-BTCUSDT}"
BOT_INTERVAL="${BOT_INTERVAL:-15m}"

log() {
  printf '[LAPS1505] %s\n' "$*"
}

need_root() {
  if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    log "Erro: execute como root."
    log "Exemplo: sudo bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/trader1505/quinze-autom-tico/${REPO_BRANCH}/scripts/install_real.sh)\""
    exit 1
  fi
}

install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    log "Docker e Docker Compose ja instalados."
    return
  fi

  log "Instalando Docker + Compose..."
  apt-get update
  apt-get install -y ca-certificates curl gnupg git
  install -m 0755 -d /etc/apt/keyrings
  if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  fi
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

prepare_repo() {
  log "Preparando codigo em ${INSTALL_DIR}..."
  if [ -d "${INSTALL_DIR}/.git" ]; then
    git -C "${INSTALL_DIR}" fetch origin "${REPO_BRANCH}"
    git -C "${INSTALL_DIR}" checkout "${REPO_BRANCH}"
    git -C "${INSTALL_DIR}" pull origin "${REPO_BRANCH}"
  else
    rm -rf "${INSTALL_DIR}"
    git clone "${REPO_URL}" "${INSTALL_DIR}"
    git -C "${INSTALL_DIR}" checkout "${REPO_BRANCH}"
  fi
}

write_env() {
  local api_key="$1"
  local api_secret="$2"
  local env_file="${INSTALL_DIR}/.env"

  cat >"${env_file}" <<EOF
BOT_SYMBOL=${BOT_SYMBOL}
BOT_INTERVAL=${BOT_INTERVAL}
BOT_EMA_SHORT=12
BOT_EMA_LONG=26
BOT_ENTRY_FRACTION=0.01
BOT_SPOT_TARGET=0.80
BOT_FUTURES_TARGET=0.20
BOT_TP_ROI=1.0
BOT_RECOVERY_MULTIPLIER=3.0
BOT_ORDER_SLICES=3
BOT_MARGIN_STRESS=0.60
BOT_MARGIN_RECOVERY=0.30
BOT_MIN_NOTIONAL=15.0
BOT_POLL_SECONDS=5
BOT_DRY_RUN=false
BOT_API_HOST=0.0.0.0
BOT_API_PORT=${BOT_PORT}
BINANCE_API_KEY=${api_key}
BINANCE_API_SECRET=${api_secret}
EOF

  chmod 600 "${env_file}"
  log "Arquivo .env criado com permissao segura (600)."
}

stop_conflicting_services() {
  local units=(
    "laps-bot-api"
    "laps-bot"
    "laps-crypto-dashboard"
    "laps-crypto"
  )
  for unit in "${units[@]}"; do
    if systemctl list-unit-files "${unit}.service" >/dev/null 2>&1; then
      systemctl stop "${unit}.service" >/dev/null 2>&1 || true
      systemctl disable "${unit}.service" >/dev/null 2>&1 || true
    fi
  done
}

start_stack() {
  log "Subindo containers..."
  docker compose -f "${INSTALL_DIR}/docker-compose.yml" --env-file "${INSTALL_DIR}/.env" down || true
  docker compose -f "${INSTALL_DIR}/docker-compose.yml" --env-file "${INSTALL_DIR}/.env" up -d --build
}

start_engine() {
  local tries=0
  local max_tries=25

  log "Aguardando API subir..."
  until curl -fsS "http://127.0.0.1:${BOT_PORT}/api/status" >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "${tries}" -ge "${max_tries}" ]; then
      log "Falha: API nao respondeu na porta ${BOT_PORT}."
      docker compose -f "${INSTALL_DIR}/docker-compose.yml" logs --tail=120
      exit 1
    fi
    sleep 2
  done

  log "Iniciando motor de trade..."
  curl -fsS -X POST "http://127.0.0.1:${BOT_PORT}/api/start" >/dev/null
}

print_summary() {
  local public_ip
  public_ip="$(hostname -I | awk '{print $1}')"
  log "Instalacao concluida."
  log "Painel: http://${public_ip}:${BOT_PORT}"
  log "Status local: curl http://127.0.0.1:${BOT_PORT}/api/status"
  log "Logs: docker compose -f ${INSTALL_DIR}/docker-compose.yml logs -f"
}

main() {
  need_root "$@"
  install_docker
  read_secret "Digite BINANCE_API_KEY (nao aparece na tela): " BINANCE_API_KEY
  read_secret "Digite BINANCE_API_SECRET (nao aparece na tela): " BINANCE_API_SECRET
  prepare_repo
  write_env "${BINANCE_API_KEY}" "${BINANCE_API_SECRET}"
  stop_conflicting_services
  start_stack
  start_engine
  print_summary
}

main "$@"
