import json
import os
import threading
import time

SIMULATION = False

LOW_VOLUME_WARNING_ML = 100

try:
    from gpiozero import OutputDevice
    from gpiozero.exc import GPIOZeroError
except ImportError:
    OutputDevice = None
    SIMULATION = True
    print("gpiozero not available - running in simulation mode")


class Pump:
    def __init__(self, key, pin, name, value=None, volume_ml=0,
                 flow_rate_ml_per_sec=1.67):
        self.key                 = key
        self.pin                 = pin
        self.name                = name
        self.value               = value
        self.volume_ml           = volume_ml
        self.flow_rate_ml_per_sec = flow_rate_ml_per_sec
        self._device             = None

        if not SIMULATION and OutputDevice:
            try:
                # active_high=False means .on() pulls pin LOW
                # which is correct for active-low relay/LED circuits
                self._device = OutputDevice(pin, active_high=True,
                                            initial_value=False)
            except GPIOZeroError as e:
                print(f"Warning: could not set up {name} on pin {pin}: {e}")

    def is_low(self):
        return self.volume_ml is not None and \
               0 < self.volume_ml < LOW_VOLUME_WARNING_ML

    def is_empty(self):
        return self.volume_ml is not None and self.volume_ml <= 0

    def pour(self, amount_ml, on_complete=None):
        duration = amount_ml / self.flow_rate_ml_per_sec

        def _run():
            if SIMULATION or not self._device:
                print(f"[SIM] {self.name} ({self.value}): "
                      f"pouring {amount_ml}ml for {duration:.1f}s")
                time.sleep(duration)
                print(f"[SIM] {self.name}: done")
            else:
                self._device.on()
                time.sleep(duration)
                self._device.off()

            if self.volume_ml is not None:
                self.volume_ml = max(0, self.volume_ml - amount_ml)

            if on_complete:
                on_complete()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    def clean(self, duration_sec=20, on_complete=None):
        def _run():
            if SIMULATION or not self._device:
                print(f"[SIM] {self.name}: cleaning for {duration_sec}s")
                time.sleep(duration_sec)
                print(f"[SIM] {self.name}: clean done")
            else:
                self._device.on()
                time.sleep(duration_sec)
                self._device.off()

            if on_complete:
                on_complete()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    def off(self):
        """Ensure pump is off - useful for emergency stop."""
        if self._device:
            self._device.off()

    def close(self):
        """Release GPIO resource."""
        if self._device:
            self._device.close()

    def to_dict(self):
        return {
            "pin":                 self.pin,
            "name":                self.name,
            "value":               self.value,
            "volume_ml":           self.volume_ml,
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
        data = {key: pump.to_dict() for key, pump in self.pumps.items()}
        self.save_raw(data)

    def save_raw(self, data):
        os.makedirs("config", exist_ok=True)
        with open(self.CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def get_pump_for_ingredient(self, ingredient):
        for pump in self.pumps.values():
            if pump.value == ingredient:
                return pump
        return None

    def get_available_ingredients(self):
        return {p.value for p in self.pumps.values()
                if p.value and not p.is_empty()}

    def get_low_pumps(self):
        return [p for p in self.pumps.values() if p.value and p.is_low()]

    def make_drink(self, ingredients, on_progress=None, on_complete=None):
        threads  = []
        max_time = 0

        with self._lock:
            for ingredient, amount_ml in ingredients.items():
                pump = self.get_pump_for_ingredient(ingredient)
                if pump:
                    t        = pump.pour(amount_ml)
                    duration = amount_ml / pump.flow_rate_ml_per_sec
                    threads.append(t)
                    if duration > max_time:
                        max_time = duration
                else:
                    print(f"Warning: no pump loaded with '{ingredient}'")

        def _wait_and_finish():
            start = time.time()
            while any(t.is_alive() for t in threads):
                elapsed = time.time() - start
                pct = min(100, int((elapsed / max_time) * 100)) \
                      if max_time > 0 else 100
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
        threads  = []
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

    def stop_all(self):
        """Emergency stop - turns off all pumps immediately."""
        for pump in self.pumps.values():
            pump.off()

    def cleanup(self):
        """Release all GPIO resources cleanly."""
        for pump in self.pumps.values():
            pump.close()
