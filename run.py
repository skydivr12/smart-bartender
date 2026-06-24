import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from pump_manager import PumpManager
from drinks import DrinkManager
from web import start_web_server
from gui import App

pm = PumpManager()
dm = DrinkManager()

# Start web server in background
start_web_server(pm, dm)

# Start GUI (this blocks until the app is closed)
app = App(pm, dm)
app.run()
