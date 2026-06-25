import json
import os

SETTINGS_PATH = "config/settings.json"

DEFAULTS = {
    "pin":          "1234",
    "fan_pin":      20,
    "fan_on_temp":  65,
    "fan_off_temp": 55,
    "prime_duration": 10
}


class SettingsManager:
    def __init__(self):
        self.data = {}
        self.load()

    def load(self):
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r") as f:
                self.data = json.load(f)
            # add any missing keys from defaults
            changed = False
            for key, val in DEFAULTS.items():
                if key not in self.data:
                    self.data[key] = val
                    changed = True
            if changed:
                self.save()
        else:
            self.data = dict(DEFAULTS)
            self.save()
        print(f"Settings loaded")

    def save(self):
        os.makedirs("config", exist_ok=True)
        with open(SETTINGS_PATH, "w") as f:
            json.dump(self.data, f, indent=2)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def check_pin(self, entered):
        return str(entered) == str(self.data.get("pin", "1234"))

    def set_pin(self, new_pin):
        self.data["pin"] = str(new_pin)
        self.save()
