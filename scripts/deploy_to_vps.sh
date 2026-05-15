#!/usr/bin/env bash
set -euo pipefail

VPS_IP="${VPS_IP:-187.124.35.57}"
VPS_USER="${VPS_USER:-root}"
REMOTE_DIR="${REMOTE_DIR:-/root/laps_crypto}"
LOCAL_DIR="${LOCAL_DIR:-$(pwd)}"

echo "Deploy para ${VPS_USER}@${VPS_IP}:${REMOTE_DIR}"

echo "[1/3] Copiando projeto para VPS..."
ssh "${VPS_USER}@${VPS_IP}" "mkdir -p '${REMOTE_DIR}'"
scp -r "${LOCAL_DIR}/." "${VPS_USER}@${VPS_IP}:${REMOTE_DIR}"

echo "[2/3] Instalando e configurando no servidor..."
ssh "${VPS_USER}@${VPS_IP}" "cd '${REMOTE_DIR}' && bash scripts/install_on_vps.sh"

echo "[3/3] Deploy concluído."
echo "Acesse o painel em: http://${VPS_IP}:8080"
