import os
import sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from pump_manager import PumpManager
from drinks import DrinkManager
from settings import SettingsManager
from fan_controller import FanController
import led_controller as leds
from web import start_web_server

pm = PumpManager()
dm = DrinkManager()
sm = SettingsManager()

# Start fan controller
fan = FanController(
    pin=sm.get("fan_pin", 20),
    on_temp_c=sm.get("fan_on_temp", 65),
    off_temp_c=sm.get("fan_off_temp", 55)
)
fan.start()

# LEDs — idle state on startup (no-op when LED_ENABLED = False)
leds.idle()

# Start web server (non-blocking, runs in background thread)
start_web_server(pm, dm, fan)

# Start GUI only if a display is available. Only App(...)'s construction is
# guarded here - that's where pygame's display init fails if there's truly
# no display (the legitimate "run headless" case). app.run() is NOT inside
# this try: if the GUI crashes after it's already up and running, we want
# that to propagate as a real, visible crash (full traceback in the log,
# process exits, kiosk_launch.sh restarts it) rather than silently falling
# into an infinite web-only loop with no indication anything went wrong -
# that's exactly what masked the pump-editing crash and left the screen
# frozen with zero feedback.
try:
    from gui import App
    app = App(pm, dm, sm)
except Exception as e:
    print(f"GUI not available ({e}) — running in web-only mode")
    print("Access the interface at http://127.0.0.1:5000")
    # Keep the process alive for the web server
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
else:
    print("GUI started successfully")
    app.run()

# Cleanup on exit
leds.cleanup()
fan.stop()