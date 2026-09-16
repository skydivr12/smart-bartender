import time
from gpiozero import OutputDevice, Button

PUMP_PINS = {
    "pump_1":  4,
    "pump_2":  15,
    "pump_3":  27,
    "pump_4":  23,
    "pump_5":  14,
    "pump_6":  17,
    "pump_7":  22,
    "pump_8":  24,
    "pump_9":  9,
    "pump_10": 8,
    "pump_11": 12,
    "pump_12": 26,
    "pump_13": 25,
    "pump_14": 7,
    "pump_15": 16,
    "pump_16": 21,
}

BUTTON_PINS = {
    "up":     13,
    "down":   19,
    "select": 6,
    "back":   5,
}

print("=== LED Test ===")
print("Each LED will light up for 1 second in order.\n")

pumps = {}
for name, pin in PUMP_PINS.items():
    # active_high=False means .on() pulls LOW which lights our LEDs
    pumps[name] = OutputDevice(pin, active_high=False, initial_value=False)

for name, device in pumps.items():
    print(f"  Testing {name}...")
    device.on()
    time.sleep(1)
    device.off()
    time.sleep(0.3)

for device in pumps.values():
    device.close()

print("\n=== All LEDs done ===")
print("\n=== Button Test ===")
print("Press each button. You have 30 seconds.")
print("Press Ctrl+C to quit early.\n")

buttons = {name: Button(pin, pull_up=True, bounce_time=0.05)
           for name, pin in BUTTON_PINS.items()}

for name, btn in buttons.items():
    btn.when_pressed = lambda n=name: print(f"  Button pressed: {n}")

try:
    time.sleep(30)
except KeyboardInterrupt:
    pass

for btn in buttons.values():
    btn.close()

print("\nTest complete.")
