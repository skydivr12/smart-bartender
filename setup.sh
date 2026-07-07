#!/bin/bash
#
# Smart Bartender deployment script — fresh Raspberry Pi OS Trixie (Desktop)
# install to a running kiosk, or update an existing install to the latest
# code. Same command either way — the script detects which mode it's in.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/skydivr12/smart-bartender/main/setup.sh | bash
#
#   Or, if you already cloned the repo (git clone, or copied off a USB stick):
#        cd smart-bartender && bash setup.sh
#
#   To deploy from a branch other than main, set REPO_BRANCH (fetch this
#   file itself from that branch too, so the two match):
#   curl -fsSL https://raw.githubusercontent.com/skydivr12/smart-bartender/touchscreen-controls/setup.sh | REPO_BRANCH=touchscreen-controls bash
#
# Must be run as your normal user (NOT root/sudo) from an interactive terminal —
# it calls sudo itself for the steps that need it, and asks for WiFi input if needed.
#
# Requirements:
#   Raspberry Pi OS Trixie (Debian 13) WITH Desktop. The bartender app runs
#   as a kiosk autostarted inside the desktop session (auto-login -> desktop
#   -> XDG autostart -> restart-on-crash wrapper), not as a headless systemd
#   service — Desktop images boot to a compositor (labwc/Wayfire) that
#   already owns the display, so this avoids fighting it for the screen.
#
set -euo pipefail

REPO_URL="https://github.com/skydivr12/smart-bartender.git"
REPO_BRANCH="${REPO_BRANCH:-main}"
INSTALL_DIR="$HOME/smart-bartender"
TARGET_HOSTNAME="bartender"
RUN_USER="$(id -un)"
AUTOSTART_DIR="$HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/bartender.desktop"
LAUNCH_SCRIPT="$INSTALL_DIR/kiosk_launch.sh"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
header()  { echo -e "\n${BOLD}--- $1 ---${NC}"; }

if [ "$EUID" -eq 0 ]; then
    error "Run this as your normal user, not root/sudo — it calls sudo itself when needed."
fi

# -----------------------------------------------------------------------------
# Detect fresh install vs update
# -----------------------------------------------------------------------------
IS_UPDATE=false
if [ -f "$AUTOSTART_FILE" ]; then
    IS_UPDATE=true
fi

echo ""
echo -e "${BOLD}=============================================${NC}"
if [ "$IS_UPDATE" = true ]; then
    echo -e "${BOLD}  Smart Bartender — Software Update          ${NC}"
else
    echo -e "${BOLD}  Smart Bartender — Fresh Install             ${NC}"
fi
echo -e "${BOLD}=============================================${NC}"
echo ""
info "Mode:   $([ "$IS_UPDATE" = true ] && echo 'UPDATE (existing installation found)' || echo 'FRESH INSTALL')"
info "Repo:   $REPO_URL"
info "Branch: $REPO_BRANCH"
info "Target: $INSTALL_DIR"
echo ""

# Keep sudo alive for the whole run so we don't get surprise password prompts mid-step.
header "Checking sudo access"
sudo -v || error "This script needs sudo access to install packages and configure the Pi."
( while true; do sudo -n true; sleep 60; done ) 2>/dev/null &
SUDO_KEEPALIVE_PID=$!
trap 'kill "$SUDO_KEEPALIVE_PID" 2>/dev/null' EXIT
success "sudo OK"

# ---------------------------------------------------------------------------
# Migration: remove the old headless/KMSDRM systemd service if present (from
# a prior Raspberry Pi OS Lite deployment) — the kiosk now launches via
# desktop autostart instead (Step 9), and leaving the old service enabled
# would fight it for the GPIO pins and port 5000.
# ---------------------------------------------------------------------------
OLD_SERVICE="/etc/systemd/system/bartender.service"
if [ -f "$OLD_SERVICE" ]; then
    header "Migrating from previous headless (systemd) install"
    sudo systemctl stop bartender 2>/dev/null || true
    sudo systemctl disable bartender 2>/dev/null || true
    sudo rm -f "$OLD_SERVICE"
    sudo systemctl daemon-reload
    success "Removed old systemd service — this install now runs via desktop autostart instead"
fi

# ---------------------------------------------------------------------------
# Step 1: fetch or update the code
#
#   - Bootstrapping onto a fresh/target Pi (curl | bash, or re-running the
#     one-liner against an existing $INSTALL_DIR): this is a known
#     deployment target, so bring it to exactly origin/$REPO_BRANCH.
#   - Running directly from a checkout you might be actively editing
#     (cd smart-bartender && bash setup.sh over SSH during development):
#     don't force-overwrite local work — try a safe fast-forward pull and
#     fall back to what's on disk if that's not possible.
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "")"

if [ -z "$SCRIPT_DIR" ] || [ ! -f "$SCRIPT_DIR/run.py" ] || [ ! -d "$SCRIPT_DIR/.git" ]; then
    header "Step 1: Fetching smart-bartender ($REPO_BRANCH)"
    command -v git >/dev/null 2>&1 || {
        sudo apt-get update -qq
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git
    }

    if [ -d "$INSTALL_DIR/.git" ]; then
        info "Existing install found at $INSTALL_DIR — updating to latest $REPO_BRANCH"
        git -C "$INSTALL_DIR" fetch origin "$REPO_BRANCH" --quiet || error "git fetch failed"
        git -C "$INSTALL_DIR" checkout "$REPO_BRANCH" --quiet 2>/dev/null || \
            git -C "$INSTALL_DIR" checkout -b "$REPO_BRANCH" "origin/$REPO_BRANCH" --quiet
        git -C "$INSTALL_DIR" reset --hard "origin/$REPO_BRANCH" --quiet
        success "Updated $INSTALL_DIR to latest $REPO_BRANCH"
    else
        git clone --branch "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR" || error "git clone failed"
        success "Cloned to $INSTALL_DIR"
    fi
    kill "$SUDO_KEEPALIVE_PID" 2>/dev/null  # exec below skips the EXIT trap, so stop it explicitly
    exec bash "$INSTALL_DIR/setup.sh"
fi

cd "$SCRIPT_DIR"
success "Running setup from $SCRIPT_DIR"

if git -C "$SCRIPT_DIR" rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
    if git -C "$SCRIPT_DIR" diff --quiet && git -C "$SCRIPT_DIR" diff --cached --quiet; then
        if git -C "$SCRIPT_DIR" pull --ff-only --quiet 2>/dev/null; then
            success "Pulled latest changes"
        else
            warn "Could not fast-forward (local commits ahead, or diverged) — continuing with what's on disk"
        fi
    else
        warn "Local changes detected — skipping auto-update so your edits aren't touched"
    fi
fi

# ---------------------------------------------------------------------------
# Step 2: Network check / interactive WiFi setup
# ---------------------------------------------------------------------------
header "Step 2: Checking network connectivity"
if ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 || ping -c1 -W3 8.8.8.8 >/dev/null 2>&1; then
    success "Network is up"
else
    warn "No internet connection detected"
    command -v nmcli >/dev/null 2>&1 || error "nmcli not found — can't configure WiFi automatically. Connect via ethernet or set up WiFi manually, then re-run."

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
            success "Connected to $WIFI_SSID"
            break
        else
            unset WIFI_PASS
            warn "Couldn't connect — check the password and try again"
        fi
    done
fi

# ---------------------------------------------------------------------------
# Step 3 / 4: System packages
# ---------------------------------------------------------------------------
header "Step 3: Updating package lists"
sudo apt-get update || error "apt-get update failed"
success "Package lists updated"

header "Step 4: Installing system packages"
export DEBIAN_FRONTEND=noninteractive

install_pkg() {
    local apt_name="$1" pip_name="$2"
    if sudo apt-get install -y "$apt_name" 2>/tmp/bartender_apt_err; then
        success "$apt_name"
    else
        warn "$apt_name not available via apt — falling back to pip ($pip_name)"
        pip3 install --break-system-packages "$pip_name" || error "could not install $pip_name via apt or pip"
        success "$pip_name (pip)"
    fi
}

sudo apt-get install -y git python3 python3-pip avahi-daemon raspi-config || error "core package install failed"
success "git, python3, python3-pip, avahi-daemon, raspi-config"
install_pkg python3-pygame "pygame==2.6.1"
install_pkg python3-gpiozero "gpiozero"
install_pkg python3-flask "Flask==3.1.3"

# gpiozero's pin factory on Trixie needs the lgpio backend — RPi.GPIO doesn't
# work against the newer kernel GPIO character-device interface.
if sudo apt-get install -y python3-lgpio 2>/dev/null; then
    success "python3-lgpio"
else
    warn "python3-lgpio not found via apt — if pumps/buttons don't respond, run: pip3 install --break-system-packages lgpio"
fi

# ---------------------------------------------------------------------------
# Step 5: Hostname -> bartender.local
# ---------------------------------------------------------------------------
header "Step 5: Setting hostname to '$TARGET_HOSTNAME'"
if [ "$(hostname)" != "$TARGET_HOSTNAME" ]; then
    sudo raspi-config nonint do_hostname "$TARGET_HOSTNAME"
    sudo systemctl restart avahi-daemon 2>/dev/null || true
    success "Hostname set — will be reachable at http://${TARGET_HOSTNAME}.local:5000 after reboot"
else
    success "Hostname already '$TARGET_HOSTNAME'"
fi

# ---------------------------------------------------------------------------
# Step 6: Desktop auto-login + screen blanking
#
#   Auto-login straight to the desktop is what makes this "no interaction" —
#   the bartender kiosk app then autostarts inside that session (Step 9).
#   Screen blanking has to be disabled too, or the touchscreen goes dark
#   mid-party with no one around to tap it awake.
# ---------------------------------------------------------------------------
header "Step 6: Configuring auto-login and screen blanking"
sudo raspi-config nonint do_boot_behaviour B4
success "Desktop auto-login enabled for $RUN_USER"
sudo raspi-config nonint do_blanking 1
success "Screen blanking disabled"
warn "Verify after first boot — if the screen still blanks, check: sudo raspi-config (Display Options > Screen Blanking)"

# ---------------------------------------------------------------------------
# Step 7: Passwordless nmcli — the on-screen WiFi setup (gui.py) runs nmcli
#   via sudo from inside the kiosk app, so it can't sit at a password
#   prompt. Scope this narrowly to nmcli only.
# ---------------------------------------------------------------------------
header "Step 7: Allowing passwordless nmcli for $RUN_USER"
SUDOERS_FILE="/etc/sudoers.d/bartender-nmcli"
echo "$RUN_USER ALL=(ALL) NOPASSWD: /usr/bin/nmcli" | sudo tee "$SUDOERS_FILE" >/dev/null
sudo chmod 440 "$SUDOERS_FILE"
if sudo visudo -cf "$SUDOERS_FILE" >/dev/null 2>&1; then
    success "sudoers rule installed"
else
    sudo rm -f "$SUDOERS_FILE"
    error "generated sudoers rule was invalid — removed it, WiFi screen needs manual sudo setup"
fi

# ---------------------------------------------------------------------------
# Step 8: Group membership — GPIO access for pumps/buttons
# ---------------------------------------------------------------------------
header "Step 8: Adding $RUN_USER to gpio,dialout groups"
sudo usermod -aG gpio,dialout "$RUN_USER"
success "Group membership updated"

# ---------------------------------------------------------------------------
# Step 9: Kiosk autostart — launches inside the desktop session rather than
#   as a headless systemd service, since the desktop compositor already owns
#   the display. The wrapper script restarts the app if it ever crashes
#   (guest-facing device at a party, no one around to notice and relaunch it).
# ---------------------------------------------------------------------------
header "Step 9: Installing kiosk autostart"

cat > "$LAUNCH_SCRIPT" <<'EOF'
#!/bin/bash
# Auto-generated by setup.sh — launches the bartender app and restarts it
# if it ever exits or crashes. Logs to kiosk.log next to this script since
# there's no systemd journal to catch stdout from a desktop-autostarted app.
cd "$(dirname "$0")"
LOG="$(dirname "$0")/kiosk.log"

while true; do
    # Keep the log from growing forever across a long event.
    if [ -f "$LOG" ] && [ "$(stat -c%s "$LOG" 2>/dev/null || echo 0)" -gt 5000000 ]; then
        : > "$LOG"
    fi
    {
        echo "=== $(date) : starting run.py ==="
        python3 run.py
        echo "=== $(date) : run.py exited, restarting in 2s ==="
    } >> "$LOG" 2>&1
    sleep 2
done
EOF
chmod +x "$LAUNCH_SCRIPT"
success "Wrote $LAUNCH_SCRIPT"

mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Smart Bartender
Exec=/bin/bash $LAUNCH_SCRIPT
X-GNOME-Autostart-enabled=true
NoDisplay=false
EOF
success "Wrote $AUTOSTART_FILE"

# ---------------------------------------------------------------------------
# Step 10: Verify — run.py already falls back to web-only mode when no
#   display is attached, so this SSH session can sanity-check the code runs
#   and the web interface responds without needing the kiosk to actually be
#   on screen yet. SDL_VIDEODRIVER=dummy keeps this check from touching the
#   real screen even if a desktop session isn't up yet to claim it first.
# ---------------------------------------------------------------------------
header "Step 10: Verifying"
cd "$SCRIPT_DIR"
SDL_VIDEODRIVER=dummy python3 run.py >/tmp/bartender_verify.log 2>&1 &
VERIFY_PID=$!

WEB_OK=0
for _ in 1 2 3 4 5 6 7 8; do
    if curl -fsS -o /dev/null "http://127.0.0.1:5000/"; then
        WEB_OK=1
        break
    fi
    sleep 1
done

kill "$VERIFY_PID" 2>/dev/null || true
wait "$VERIFY_PID" 2>/dev/null || true

if [ "$WEB_OK" -eq 1 ]; then
    success "Code runs and web interface responds"
else
    warn "Web interface didn't respond in time — check /tmp/bartender_verify.log"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo
echo -e "${BOLD}=============================================${NC}"
echo -e "${BOLD}  $([ "$IS_UPDATE" = true ] && echo 'Update' || echo 'Deployment') Complete${NC}"
echo -e "${BOLD}=============================================${NC}"
echo
echo -e "  Install dir:  ${BLUE}$INSTALL_DIR${NC}"
echo -e "  Autostart:    ${BLUE}$AUTOSTART_FILE${NC}"
echo -e "  Kiosk log:    ${BLUE}$INSTALL_DIR/kiosk.log${NC}"
echo -e "  Web UI:       ${BLUE}http://${TARGET_HOSTNAME}.local:5000${NC} (also reachable by IP)"
echo
echo -e "  ${YELLOW}Reboot to apply auto-login, screen blanking, and (re)launch the kiosk:${NC}"
echo -e "    sudo reboot"
echo
echo "  No systemd unit runs the GUI anymore — it's autostarted inside the"
echo "  desktop session and logs to kiosk.log. Tail it with:"
echo "    tail -f $INSTALL_DIR/kiosk.log"
echo
