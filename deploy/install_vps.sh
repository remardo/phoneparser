#!/usr/bin/env bash
set -euo pipefail

# One-click installer for Debian/Ubuntu VPS
# - Installs python3/git
# - Clones repo into /opt/phoneparser
# - Creates venv and installs deps
# - Creates and starts systemd services (bot + admin)
#
# Optional env vars:
#   REPO_URL   - default https://github.com/remardo/phoneparser.git
#   BRANCH     - default main
#   APP_DIR    - default /opt/phoneparser
#   APP_USER   - default phoneparser
#   PORT       - default 8000 (admin UI)
#   SA_JSON_B64        - base64 of Google Service Account JSON (writes to src/service-acount-sheets.json)
#   SESSIONS_JSON_B64  - base64 of src/sessions.json content

REPO_URL=${REPO_URL:-"https://github.com/remardo/phoneparser.git"}
BRANCH=${BRANCH:-"main"}
APP_DIR=${APP_DIR:-"/opt/phoneparser"}
APP_USER=${APP_USER:-"phoneparser"}
PORT=${PORT:-"8000"}

log() { echo -e "[install] $*"; }

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "Please run as root (use: sudo bash install_vps.sh)" >&2
  exit 1
fi

if command -v apt >/dev/null 2>&1; then
  log "Installing packages via apt..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y git python3 python3-venv python3-pip curl ca-certificates
else
  echo "Unsupported distro (expects apt). Install git, python3, python3-venv, python3-pip manually and re-run." >&2
  exit 1
fi

# Create dedicated system user
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  log "Creating system user $APP_USER"
  useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
fi

log "Preparing app directory: $APP_DIR"
mkdir -p "$APP_DIR"
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

# Clone or update repository
if [ ! -d "$APP_DIR/.git" ]; then
  log "Cloning $REPO_URL (branch: $BRANCH)"
  sudo -u "$APP_USER" git clone -b "$BRANCH" --depth=1 "$REPO_URL" "$APP_DIR"
else
  log "Updating repository..."
  sudo -u "$APP_USER" git -C "$APP_DIR" fetch --depth=1 origin "$BRANCH"
  sudo -u "$APP_USER" git -C "$APP_DIR" reset --hard "origin/$BRANCH"
fi

# Python virtual environment
if [ ! -d "$APP_DIR/.venv" ]; then
  log "Creating virtual env"
  sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
fi
log "Upgrading pip"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" -m pip install --upgrade pip wheel

log "Installing Python dependencies"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install \
  beautifulsoup4 bs4 \
  google-auth gspread \
  loguru \
  python-dotenv \
  telethon \
  fastapi uvicorn jinja2

# Write secrets from env if provided
if [ -n "${SA_JSON_B64:-}" ]; then
  log "Writing service account json from SA_JSON_B64"
  install -d -m 0755 "$APP_DIR/src"
  echo "$SA_JSON_B64" | base64 -d > "$APP_DIR/src/service-acount-sheets.json"
  chown "$APP_USER":"$APP_USER" "$APP_DIR/src/service-acount-sheets.json"
  chmod 600 "$APP_DIR/src/service-acount-sheets.json"
fi

if [ -n "${SESSIONS_JSON_B64:-}" ]; then
  log "Writing sessions.json from SESSIONS_JSON_B64"
  install -d -m 0755 "$APP_DIR/src"
  echo "$SESSIONS_JSON_B64" | base64 -d > "$APP_DIR/src/sessions.json"
  chown "$APP_USER":"$APP_USER" "$APP_DIR/src/sessions.json"
  chmod 600 "$APP_DIR/src/sessions.json"
fi

# Ensure placeholder sessions.json exists (to avoid immediate crash)
if [ ! -f "$APP_DIR/src/sessions.json" ]; then
  echo "{}" > "$APP_DIR/src/sessions.json"
  chown "$APP_USER":"$APP_USER" "$APP_DIR/src/sessions.json"
fi

# Systemd services
BOT_UNIT=/etc/systemd/system/phoneparser-bot.service
ADMIN_UNIT=/etc/systemd/system/phoneparser-admin.service

log "Creating systemd unit: $BOT_UNIT"
cat > "$BOT_UNIT" <<EOF
[Unit]
Description=Parsing Phone Numbers Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

log "Creating systemd unit: $ADMIN_UNIT"
cat > "$ADMIN_UNIT" <<EOF
[Unit]
Description=Parsing Admin Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/.venv/bin/python -m uvicorn admin_app:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

log "Enabling and starting services"
systemctl daemon-reload
systemctl enable --now phoneparser-bot.service
systemctl enable --now phoneparser-admin.service || true

# Optional: open firewall
if command -v ufw >/dev/null 2>&1; then
  if ufw status | grep -qi active; then
    ufw allow "$PORT"/tcp || true
  fi
fi

log "Install complete."
cat <<MSG
Next steps:
  1) Upload your Telegram .session files into $APP_DIR (repo root).
  2) Place Google SA key at $APP_DIR/src/service-acount-sheets.json
     (or export SA_JSON_B64 and re-run this script to auto-provision)
  3) Edit $APP_DIR/src/sessions.json with your API creds.
  4) Check services and logs:
       systemctl status phoneparser-bot.service
       systemctl status phoneparser-admin.service
       journalctl -u phoneparser-bot.service -f
  5) Admin UI: http://<server-ip>:$PORT (health: /health)
MSG
