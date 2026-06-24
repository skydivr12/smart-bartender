import json
import os
import threading
import time

# When SIMULATION = True, no real GPIO is used.
# LEDs/pumps just print to the screen instead.
# Set this to False when real hardware is connected.
SIMULATION = True

LOW_VOLUME_WARNING_ML = 100  # warn when a pump has less than this much liquid left

try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
except (ImportError, RuntimeError):
    GPIO = None
    print("GPIO not available - running in simulation mode")
    SIMULATION = True


class Pump:
    def __init__(self, key, pin, name, value=None, volume_ml=0, flow_rate_ml_per_sec=1.67):
        """
        key          : unique id e.g. 'pump_1'
        pin          : GPIO pin number
        name         : display name e.g. 'Pump 1'
        value        : what liquid is loaded e.g. 'gin'
        volume_ml    : how much liquid remains in ml
        flow_rate    : ml per second this pump delivers (default ~100ml/min)
        """
        self.key = key
        self.pin = pin
        self.name = name
        self.value = value
        self.volume_ml = volume_ml
        self.flow_rate_ml_per_sec = flow_rate_ml_per_sec

        if not SIMULATION and GPIO:
            GPIO.setup(self.pin, GPIO.OUT, initial=GPIO.HIGH)

    def is_low(self):
        return self.volume_ml is not None and self.volume_ml < LOW_VOLUME_WARNING_ML

    def is_empty(self):
        return self.volume_ml is not None and self.volume_ml <= 0

    def pour(self, amount_ml, on_complete=None):
        """
        Runs the pump long enough to dispense amount_ml.
        Runs in a thread so it doesn't block the rest of the program.
        """
        duration = amount_ml / self.flow_rate_ml_per_sec

        def _run():
            if SIMULATION:
                print(f"[SIM] {self.name} ({self.value}): pouring {amount_ml}ml "
                      f"for {duration:.1f}s")
                time.sleep(duration)
                print(f"[SIM] {self.name}: done")
            else:
                GPIO.output(self.pin, GPIO.LOW)   # LOW turns relay ON
                time.sleep(duration)
                GPIO.output(self.pin, GPIO.HIGH)  # HIGH turns relay OFF

            # Subtract the poured amount from remaining volume
            if self.volume_ml is not None:
                self.volume_ml = max(0, self.volume_ml - amount_ml)

            if on_complete:
                on_complete()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    def clean(self, duration_sec=20, on_complete=None):
        """Runs pump for a fixed time to flush the tube."""
        def _run():
            if SIMULATION:
                print(f"[SIM] {self.name}: cleaning for {duration_sec}s")
                time.sleep(duration_sec)
                print(f"[SIM] {self.name}: clean done")
            else:
                GPIO.output(self.pin, GPIO.LOW)
                time.sleep(duration_sec)
                GPIO.output(self.pin, GPIO.HIGH)

            if on_complete:
                on_complete()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    def to_dict(self):
        """Converts this pump to a dictionary so it can be saved to JSON."""
        return {
            "pin": self.pin,
            "name": self.name,
            "value": self.value,
            "volume_ml": self.volume_ml,
            "flow_rate_ml_per_sec": self.flow_rate_ml_per_sec
        }


class PumpManager:
    CONFIG_PATH = "config/pumps.json"

    DEFAULT_PUMPS = {
        "pump_1": {"pin": 17, "name": "Pump 1", "value": None, "volume_ml": 0},
        "pump_2": {"pin": 27, "name": "Pump 2", "value": None, "volume_ml": 0},
        "pump_3": {"pin": 22, "name": "Pump 3", "value": None, "volume_ml": 0},
        "pump_4": {"pin": 23, "name": "Pump 4", "value": None, "volume_ml": 0},
        "pump_5": {"pin": 24, "name": "Pump 5", "value": None, "volume_ml": 0},
        "pump_6": {"pin": 25, "name": "Pump 6", "value": None, "volume_ml": 0},
        "pump_7": {"pin": 12, "name": "Pump 7", "value": None, "volume_ml": 0},
        "pump_8": {"pin": 16, "name": "Pump 8", "value": None, "volume_ml": 0},
    }

    def __init__(self):
        self.pumps = {}
        self._lock = threading.Lock()
        self.load()

    def load(self):
        """Loads pump config from file, or creates defaults if file doesn't exist."""
        if os.path.exists(self.CONFIG_PATH):
            with open(self.CONFIG_PATH, "r") as f:
                data = json.load(f)
        else:
            data = self.DEFAULT_PUMPS
            self.save_raw(data)

        self.pumps = {}
        for key, cfg in data.items():
            self.pumps[key] = Pump(
                key=key,
                pin=cfg["pin"],
                name=cfg["name"],
                value=cfg.get("value"),
                volume_ml=cfg.get("volume_ml", 0),
                flow_rate_ml_per_sec=cfg.get("flow_rate_ml_per_sec", 1.67)
            )
        print(f"Loaded {len(self.pumps)} pumps")

    def save(self):
        """Saves current pump state to file."""
        data = {key: pump.to_dict() for key, pump in self.pumps.items()}
        self.save_raw(data)

    def save_raw(self, data):
        os.makedirs("config", exist_ok=True)
        with open(self.CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def get_pump_for_ingredient(self, ingredient):
        """Finds which pump has a given ingredient loaded."""
        for pump in self.pumps.values():
            if pump.value == ingredient:
                return pump
        return None

    def get_available_ingredients(self):
        """Returns a set of ingredients currently loaded across all pumps."""
        return {p.value for p in self.pumps.values() if p.value and not p.is_empty()}

    def get_low_pumps(self):
        """Returns a list of pumps that are running low."""
        return [p for p in self.pumps.values() if p.value and p.is_low()]

    def make_drink(self, ingredients, on_progress=None, on_complete=None):
        """
        Pours a drink given a dict of {ingredient: amount_ml}.
        All pumps run simultaneously, just like a real bartender.
        on_progress: called with (percent_complete) as the drink pours
        on_complete: called when all pumps are done
        """
        threads = []
        max_time = 0

        with self._lock:
            for ingredient, amount_ml in ingredients.items():
                pump = self.get_pump_for_ingredient(ingredient)
                if pump:
                    t = pump.pour(amount_ml)
                    threads.append(t)
                    duration = amount_ml / pump.flow_rate_ml_per_sec
                    if duration > max_time:
                        max_time = duration
                else:
                    print(f"Warning: no pump loaded with '{ingredient}'")

        def _wait_and_finish():
            start = time.time()
            while any(t.is_alive() for t in threads):
                elapsed = time.time() - start
                pct = min(100, int((elapsed / max_time) * 100)) if max_time > 0 else 100
                if on_progress:
                    on_progress(pct)
                time.sleep(0.1)
            if on_progress:
                on_progress(100)
            self.save()
            if on_complete:
                on_complete()

        monitor = threading.Thread(target=_wait_and_finish, daemon=True)
        monitor.start()
        return max_time

    def clean_all(self, on_progress=None, on_complete=None):
        """Runs all pumps simultaneously to flush tubes."""
        threads = []
        duration = 20

        with self._lock:
            for pump in self.pumps.values():
                t = pump.clean(duration_sec=duration)
                threads.append(t)

        def _wait_and_finish():
            start = time.time()
            while any(t.is_alive() for t in threads):
                elapsed = time.time() - start
                pct = min(100, int((elapsed / duration) * 100))
                if on_progress:
                    on_progress(pct)
                time.sleep(0.1)
            if on_progress:
                on_progress(100)
            if on_complete:
                on_complete()

        monitor = threading.Thread(target=_wait_and_finish, daemon=True)
        monitor.start()

    def cleanup_gpio(self):
        """Call this when the program exits."""
        if not SIMULATION and GPIO:
            GPIO.cleanup()
