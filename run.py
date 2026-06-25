import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from pump_manager import PumpManager
from drinks import DrinkManager
from settings import SettingsManager
from fan_controller import FanController
from web import start_web_server
from gui import App

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

# Start web server
start_web_server(pm, dm, fan)

# Start GUI
app = App(pm, dm, sm)
app.run()

# Cleanup on exit
fan.stop()
