import threading
import time

SIMULATION = False

try:
    from gpiozero import OutputDevice
    from gpiozero.exc import GPIOZeroError
except ImportError:
    OutputDevice = None
    SIMULATION = True


def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return float(f.read()) / 1000.0
    except Exception:
        return 0.0


class FanController:
    """
    Monitors CPU temperature and controls a relay-switched fan.
    Runs in a background thread — just call start() and forget it.

    Fan turns ON  when temp rises above on_temp_c.
    Fan turns OFF when temp falls below off_temp_c.
    This hysteresis prevents rapid on/off cycling.
    """

    def __init__(self, pin, on_temp_c=65, off_temp_c=55,
                 check_interval=10):
        self.pin            = pin
        self.on_temp_c      = on_temp_c
        self.off_temp_c     = off_temp_c
        self.check_interval = check_interval
        self.fan_on         = False
        self._device        = None
        self._thread        = None
        self._running       = False

        if not SIMULATION and OutputDevice:
            try:
                self._device = OutputDevice(
                    pin, active_high=True, initial_value=False)
                print(f"Fan controller initialised on GPIO {pin}")
            except GPIOZeroError as e:
                print(f"Fan controller: could not set up pin {pin}: {e}")

    def _run(self):
        while self._running:
            temp = get_cpu_temp()

            if not self.fan_on and temp >= self.on_temp_c:
                self._set_fan(True)
                print(f"Fan ON  — CPU temp {temp:.1f}°C "
                      f"(threshold {self.on_temp_c}°C)")

            elif self.fan_on and temp <= self.off_temp_c:
                self._set_fan(False)
                print(f"Fan OFF — CPU temp {temp:.1f}°C "
                      f"(threshold {self.off_temp_c}°C)")

            time.sleep(self.check_interval)

    def _set_fan(self, state):
        self.fan_on = state
        if self._device:
            if state:
                self._device.on()
            else:
                self._device.off()

    def start(self):
        self._running = True
        self._thread  = threading.Thread(
            target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._set_fan(False)
        if self._device:
            self._device.close()

    def status(self):
        return {
            "temp_c":      round(get_cpu_temp(), 1),
            "fan_on":      self.fan_on,
            "on_temp_c":   self.on_temp_c,
            "off_temp_c":  self.off_temp_c,
        }
