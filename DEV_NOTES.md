# Development Setup

## PC workflow (web-only mode)
GPIO and hardware are automatically simulated when gpiozero is unavailable.
pygame GUI is skipped gracefully when no display is available.

### First time setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Start the app
```bash
./start.sh
```

- Web interface at http://127.0.0.1:5000
- Pump activity prints to terminal as [SIM] messages
- Press Ctrl+C to stop

## Pi workflow

### Fresh install (Raspberry Pi OS Lite)
```bash
git clone https://github.com/skydivr12/smart-bartender.git
cd smart-bartender
bash setup.sh
```
Installs system packages, configures the bartender.local hostname, sets up the
`bartender` systemd service (auto-starts on boot, runs pygame via the KMSDRM
driver since Lite has no desktop session), and starts it. See the comment
block at the top of `setup.sh` for the curl-based one-liner.

### Updating an already-deployed Pi
```bash
cd ~/smart-bartender
git pull
sudo systemctl restart bartender
```
GPIO and pygame GUI activate automatically on real hardware.
