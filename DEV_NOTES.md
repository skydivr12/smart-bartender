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
```bash
cd ~/smart-bartender
git pull
python3 run.py
```
GPIO and pygame GUI activate automatically on real hardware.
