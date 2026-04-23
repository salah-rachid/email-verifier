#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root: sudo bash deploy_vm2.sh"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

APP_USER="${APP_USER:-emailverifier}"
APP_GROUP="${APP_GROUP:-${APP_USER}}"
APP_DIR="${APP_DIR:-/opt/emailverifier}"
VENV_DIR="${VENV_DIR:-${APP_DIR}/.venv}"
REPO_URL="${REPO_URL:-https://github.com/your-org/emailverifier.git}"
APP_BRANCH="${APP_BRANCH:-main}"
SERVICE_NAME="${SERVICE_NAME:-emailverifier-probe}"
CRON_FILE="${CRON_FILE:-/etc/cron.d/emailverifier-probe-reset}"

echo "[1/7] Updating system packages..."
apt update
apt upgrade -y

echo "[2/7] Installing system dependencies..."
apt install -y \
  cron \
  git \
  python3 \
  python3-pip \
  python3-venv \
  ufw

echo "[3/7] Preparing application user and directories..."
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "${APP_USER}"
fi

mkdir -p "${APP_DIR}"

if [[ -d "${APP_DIR}/.git" ]]; then
  echo "[4/7] Updating existing repository..."
  git -C "${APP_DIR}" fetch --all --prune
  git -C "${APP_DIR}" checkout "${APP_BRANCH}"
  git -C "${APP_DIR}" pull --ff-only origin "${APP_BRANCH}"
else
  echo "[4/7] Cloning repository..."
  rm -rf "${APP_DIR}"
  git clone --branch "${APP_BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"

echo "[5/7] Creating Python virtual environment and installing probe dependencies..."
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install flask dnspython

echo "[6/7] Creating systemd service..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=EmailVerifier Probe Server
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${APP_DIR}
ExecStart=${VENV_DIR}/bin/python probe_server/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"

echo "[7/7] Configuring firewall and midnight reset..."
ufw allow 22/tcp
ufw allow 8080/tcp
ufw --force enable

cat > "${CRON_FILE}" <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Restarting the probe service at midnight resets the in-memory probes_today counter.
0 0 * * * root /bin/systemctl restart ${SERVICE_NAME}
EOF

chmod 644 "${CRON_FILE}"
systemctl enable --now cron
systemctl restart cron

echo
echo "VM2 deployment complete."
echo "Service status: systemctl status ${SERVICE_NAME}"
