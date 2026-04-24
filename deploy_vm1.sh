#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script as root: sudo bash deploy_vm1.sh"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

APP_USER="${APP_USER:-emailverifier}"
APP_GROUP="${APP_GROUP:-${APP_USER}}"
APP_DIR="${APP_DIR:-/opt/emailverifier}"
VENV_DIR="${VENV_DIR:-${APP_DIR}/.venv}"
REPO_URL="${REPO_URL:-https://github.com/your-org/emailverifier.git}"
APP_BRANCH="${APP_BRANCH:-main}"
SERVICE_NAME="${SERVICE_NAME:-emailverifier}"
ENV_FILE="${ENV_FILE:-/etc/emailverifier/backend.env}"
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-available/emailverifier.conf}"
SERVER_NAME="${SERVER_NAME:-_}"

echo "[1/8] Updating system packages..."
apt update
apt upgrade -y

echo "[2/8] Installing system dependencies..."
apt install -y \
  git \
  nginx \
  python3 \
  python3-pip \
  python3-venv \
  ufw

echo "[3/8] Preparing application user and directories..."
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "${APP_USER}"
fi

mkdir -p "${APP_DIR}"
mkdir -p "$(dirname "${ENV_FILE}")"

if [[ -d "${APP_DIR}/.git" ]]; then
  echo "[4/8] Updating existing repository..."
  git -C "${APP_DIR}" fetch --all --prune
  git -C "${APP_DIR}" checkout "${APP_BRANCH}"
  git -C "${APP_DIR}" pull --ff-only origin "${APP_BRANCH}"
else
  echo "[4/8] Cloning repository..."
  rm -rf "${APP_DIR}"
  git clone --branch "${APP_BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"

echo "[5/8] Creating Python virtual environment and installing requirements..."
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[6/8] Writing environment file template..."
  cat > "${ENV_FILE}" <<EOF
DATABASE_URL=postgresql://postgres:password@db-host:5432/emailverifier
REDIS_URL=redis://default:password@redis-host:6379/0
R2_BUCKET=emailverifier-results
R2_ACCOUNT_ID=your-cloudflare-account-id
R2_ACCESS_KEY_ID=your-r2-access-key
R2_SECRET_ACCESS_KEY=your-r2-secret-key
PROBE_SERVER_IP=84.8.217.135
VALIDATION_WORKERS=4
DEFAULT_USER_ID=00000000-0000-0000-0000-000000000000
PORT=5000
EOF
  chmod 600 "${ENV_FILE}"
fi

echo "[7/8] Creating systemd service..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=EmailVerifier Flask Backend
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/python backend/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"

echo "[8/8] Configuring nginx and firewall..."
cat > "${NGINX_SITE}" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${SERVER_NAME};

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sf "${NGINX_SITE}" /etc/nginx/sites-enabled/emailverifier.conf
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl restart nginx

ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo
echo "VM1 deployment complete."
echo "Edit ${ENV_FILE} with real secrets if you have not done so already."
echo "Service status: systemctl status ${SERVICE_NAME}"
