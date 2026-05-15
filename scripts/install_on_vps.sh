#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
SERVICE_NAME="${SERVICE_NAME:-laps-crypto-dashboard}"
INSTALL_SYSTEMD="${INSTALL_SYSTEMD:-1}"

if [[ ! -f "${PROJECT_DIR}/requirements.txt" ]]; then
  echo "Erro: requirements.txt não encontrado em ${PROJECT_DIR}"
  exit 1
fi

echo "[1/7] Instalando dependências do sistema..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip

echo "[2/7] Criando ambiente virtual..."
python3 -m venv "${PROJECT_DIR}/.venv"

echo "[3/7] Atualizando pip e instalando dependências Python..."
"${PROJECT_DIR}/.venv/bin/pip" install --upgrade pip
"${PROJECT_DIR}/.venv/bin/pip" install -r "${PROJECT_DIR}/requirements.txt"

if [[ ! -f "${PROJECT_DIR}/.env" ]]; then
  echo "[4/7] Criando arquivo .env a partir de .env.example..."
  cp "${PROJECT_DIR}/.env.example" "${PROJECT_DIR}/.env"
else
  echo "[4/7] Arquivo .env já existe; mantendo configuração atual."
fi

if [[ "${INSTALL_SYSTEMD}" != "1" ]]; then
  echo "[5/7] INSTALL_SYSTEMD=0, pulando configuração do systemd."
  echo "Instalação concluída."
  exit 0
fi

if [[ ! -f "${PROJECT_DIR}/deploy/systemd/laps-crypto-dashboard.service.template" ]]; then
  echo "Erro: template de service não encontrado."
  exit 1
fi

echo "[5/7] Gerando unit file do systemd..."
WORKDIR_ESCAPED="$(printf '%s' "${PROJECT_DIR}" | sed 's/[\/&]/\\&/g')"
USER_ESCAPED="$(id -un | sed 's/[\/&]/\\&/g')"
GROUP_ESCAPED="$(id -gn | sed 's/[\/&]/\\&/g')"

sed \
  -e "s/__WORKDIR__/${WORKDIR_ESCAPED}/g" \
  -e "s/__USER__/${USER_ESCAPED}/g" \
  -e "s/__GROUP__/${GROUP_ESCAPED}/g" \
  "${PROJECT_DIR}/deploy/systemd/laps-crypto-dashboard.service.template" \
  > "/etc/systemd/system/${SERVICE_NAME}.service"

echo "[6/7] Habilitando e iniciando serviço..."
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"
systemctl restart "${SERVICE_NAME}.service"

echo "[7/7] Status do serviço:"
systemctl --no-pager --full status "${SERVICE_NAME}.service" || true

echo ""
echo "Instalação concluída."
echo "Comandos úteis:"
echo "  systemctl restart ${SERVICE_NAME}"
echo "  systemctl status ${SERVICE_NAME}"
echo "  journalctl -u ${SERVICE_NAME} -f"
