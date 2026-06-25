import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from pump_manager import PumpManager
from drinks import DrinkManager
from settings import SettingsManager
from web import start_web_server
from gui import App

pm = PumpManager()
dm = DrinkManager()
sm = SettingsManager()

start_web_server(pm, dm)

app = App(pm, dm, sm)
app.run()
