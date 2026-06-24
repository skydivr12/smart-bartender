import os
import sys

# Make sure we always run from the project directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from pump_manager import PumpManager
from drinks import DrinkManager
from gui import App

pm = PumpManager()
dm = DrinkManager()
app = App(pm, dm)
app.run()
