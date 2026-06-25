# Development Setup

## Running on PC (simulation mode)
GPIO and hardware are automatically simulated when gpiozero is unavailable.

### First time setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Start the app
```bash
source venv/bin/activate
python3 run.py
```

- GUI opens via WSLg on Windows desktop
- Web interface at http://127.0.0.1:5000
- Pump activity prints to terminal as [SIM] messages

## Running on real Pi
```bash
git pull
python3 run.py
```
GPIO activates automatically when gpiozero is available.
