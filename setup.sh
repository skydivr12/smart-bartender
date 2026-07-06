#!/bin/bash
#
# Smart Bartender deployment script — fresh Raspberry Pi OS Lite to running bartender.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/skydivr12/smart-bartender/main/setup.sh | bash
#
#   Or, if you already cloned the repo (git clone, or copied off a USB stick):
#        cd smart-bartender && bash setup.sh
#
# Must be run as your normal user (NOT root/sudo) from an interactive terminal —
# it calls sudo itself for the steps that need it, and asks for WiFi input if needed.

set -euo pipefail

REPO_URL="https://github.com/skydivr12/smart-bartender.git"
INSTALL_DIR="$HOME/smart-bartender"
SERVICE_NAME="bartender"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
TARGET_HOSTNAME="bartender"
RUN_USER="$(id -un)"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; CYAN='\033[0;36m'; NC='\033[0m'
step() { echo -e "\n${CYAN}==>${NC} $1"; }
ok()   { echo -e "${GREEN}  ✓${NC} $1"; }
warn() { echo -e "${YELLOW}  !${NC} $1"; }
fail() { echo -e "${RED}  ✗ $1${NC}"; exit 1; }

if [ "$EUID" -eq 0 ]; then
    fail "Run this as your normal user, not root/sudo — it calls sudo itself when needed."
fi

# Keep sudo alive for the whole run so we don't get surprise password prompts mid-step.
step "Checking sudo access"
sudo -v || fail "This script needs sudo access to install packages and the systemd service."
( while true; do sudo -n true; sleep 60; done ) 2>/dev/null &
SUDO_KEEPALIVE_PID=$!
trap 'kill "$SUDO_KEEPALIVE_PID" 2>/dev/null' EXIT
ok "sudo OK"

# ---------------------------------------------------------------------------
# 0. Bootstrap: if this script isn't already sitting inside a clone of the
#    repo, clone it and re-run from there. Running from a USB-stick copy of
#    the repo works the same way — it already contains run.py + .git, so
#    this block is skipped entirely.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "")"
if [ -z "$SCRIPT_DIR" ] || [ ! -f "$SCRIPT_DIR/run.py" ] || [ ! -d "$SCRIPT_DIR/.git" ]; then
    step "Fetching smart-bartender"
    command -v git >/dev/null 2>&1 || {
        sudo apt-get update -qq
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git
    }

    if [ -d "$INSTALL_DIR/.git" ]; then
        ok "Already cloned at $INSTALL_DIR"
    else
        git clone "$REPO_URL" "$INSTALL_DIR" || fail "git clone failed"
    fi
    ok "Cloned to $INSTALL_DIR — continuing setup from there"
    kill "$SUDO_KEEPALIVE_PID" 2>/dev/null  # exec below skips the EXIT trap, so stop it explicitly
    exec bash "$INSTALL_DIR/setup.sh"
fi

cd "$SCRIPT_DIR"
ok "Running setup from $SCRIPT_DIR"

# ---------------------------------------------------------------------------
# 1. Network check / interactive WiFi setup
# ---------------------------------------------------------------------------
step "Checking network connectivity"
if ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 || ping -c1 -W3 8.8.8.8 >/dev/null 2>&1; then
    ok "Network is up"
else
    warn "No internet connection detected"
    command -v nmcli >/dev/null 2>&1 || fail "nmcli not found — can't configure WiFi automatically. Connect via ethernet or set up WiFi manually, then re-run."

    while true; do
        echo "Scanning for WiFi networks..."
        sudo nmcli dev wifi rescan >/dev/null 2>&1 || true
        sleep 2
        nmcli -t -f SSID dev wifi list 2>/dev/null | awk -F: '$1!=""' | sort -u || true

        echo -n "WiFi network name (SSID): "
        read -r WIFI_SSID < /dev/tty
        echo -n "WiFi password: "
        read -rs WIFI_PASS < /dev/tty
        echo

        if sudo nmcli dev wifi connect "$WIFI_SSID" password "$WIFI_PASS"; then
            unset WIFI_PASS
            ok "Connected to $WIFI_SSID"
            break
        else
            unset WIFI_PASS
            warn "Couldn't connect — check the password and try again"
        fi
    done
fi

# ---------------------------------------------------------------------------
# 2. System packages
# ---------------------------------------------------------------------------
step "Updating package lists"
sudo apt-get update || fail "apt-get update failed"
ok "Package lists updated"

step "Installing system packages"
export DEBIAN_FRONTEND=noninteractive

install_pkg() {
    local apt_name="$1" pip_name="$2"
    if sudo apt-get install -y "$apt_name" 2>/tmp/bartender_apt_err; then
        ok "$apt_name"
    else
        warn "$apt_name not available via apt — falling back to pip ($pip_name)"
        pip3 install --break-system-packages "$pip_name" || fail "could not install $pip_name via apt or pip"
        ok "$pip_name (pip)"
    fi
}

sudo apt-get install -y git python3 python3-pip avahi-daemon || fail "core package install failed"
ok "git, python3, python3-pip, avahi-daemon"
install_pkg python3-pygame "pygame==2.6.1"
install_pkg python3-gpiozero "gpiozero"
install_pkg python3-flask "Flask==3.1.3"

# gpiozero's pin factory on Bookworm/Trixie needs the lgpio backend — RPi.GPIO
# doesn't work against the newer kernel GPIO character-device interface.
if sudo apt-get install -y python3-lgpio 2>/dev/null; then
    ok "python3-lgpio"
else
    warn "python3-lgpio not found via apt — if pumps/buttons don't respond, run: pip3 install --break-system-packages lgpio"
fi

# ---------------------------------------------------------------------------
# 3. Hostname -> bartender.local
# ---------------------------------------------------------------------------
step "Setting hostname to '$TARGET_HOSTNAME'"
if [ "$(hostname)" != "$TARGET_HOSTNAME" ]; then
    if command -v raspi-config >/dev/null 2>&1; then
        sudo raspi-config nonint do_hostname "$TARGET_HOSTNAME"
    else
        sudo hostnamectl set-hostname "$TARGET_HOSTNAME"
        sudo sed -i "s/127\.0\.1\.1.*/127.0.1.1\t$TARGET_HOSTNAME/" /etc/hosts
    fi
    sudo systemctl restart avahi-daemon 2>/dev/null || true
    ok "Hostname set — will be reachable at http://${TARGET_HOSTNAME}.local:5000 after reboot"
else
    ok "Hostname already '$TARGET_HOSTNAME'"
fi

# ---------------------------------------------------------------------------
# 4. Passwordless nmcli — the on-screen WiFi setup (gui.py) runs nmcli via
#    sudo from inside the unattended systemd service, so it can't sit at a
#    password prompt. Scope this narrowly to nmcli only.
# ---------------------------------------------------------------------------
step "Allowing passwordless nmcli for $RUN_USER"
SUDOERS_FILE="/etc/sudoers.d/bartender-nmcli"
echo "$RUN_USER ALL=(ALL) NOPASSWD: /usr/bin/nmcli" | sudo tee "$SUDOERS_FILE" >/dev/null
sudo chmod 440 "$SUDOERS_FILE"
if sudo visudo -cf "$SUDOERS_FILE" >/dev/null 2>&1; then
    ok "sudoers rule installed"
else
    sudo rm -f "$SUDOERS_FILE"
    fail "generated sudoers rule was invalid — removed it, WiFi screen needs manual sudo setup"
fi

# ---------------------------------------------------------------------------
# 5. Group membership — GPIO + KMSDRM (direct video/render device access,
#    since Lite has no desktop session to own the display for us)
# ---------------------------------------------------------------------------
step "Adding $RUN_USER to gpio,video,render,dialout groups"
sudo usermod -aG gpio,video,render,dialout "$RUN_USER"
ok "Group membership updated"

# ---------------------------------------------------------------------------
# 6. systemd service
# ---------------------------------------------------------------------------
step "Installing systemd service"
sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Smart Bartender
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$SCRIPT_DIR
Environment=SDL_VIDEODRIVER=kmsdrm
ExecStart=/usr/bin/python3 $SCRIPT_DIR/run.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME" >/dev/null
sudo systemctl restart "$SERVICE_NAME"
ok "Service installed and started"

# ---------------------------------------------------------------------------
# 7. Verify
# ---------------------------------------------------------------------------
step "Verifying"
sleep 3
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
    fail "Service did not start — check: sudo journalctl -u $SERVICE_NAME -e"
fi
ok "Service is running"

WEB_OK=0
for _ in 1 2 3 4 5; do
    if curl -fsS -o /dev/null "http://127.0.0.1:5000/"; then
        WEB_OK=1
        break
    fi
    sleep 1
done
if [ "$WEB_OK" -eq 1 ]; then
    ok "Web interface responding"
else
    warn "Web interface not responding yet — give it a few more seconds, or check: sudo journalctl -u $SERVICE_NAME -e"
fi

echo
echo -e "${GREEN}Setup complete.${NC} Visit http://${TARGET_HOSTNAME}.local:5000 from a phone or laptop on the same network."
echo "Group membership changes for the GUI's display access take full effect after a reboot — recommended: sudo reboot"
