# =============================================================================
# LED_ENABLED: set to True when addressable LEDs are physically wired.
# When False, all methods are no-ops — no import errors, no crashes.
# GPIO 18 (PWM) is reserved as the data pin for the LED strip.
# NOTE: rpi_ws281x requires the app to run as root (sudo) on real hardware.
# =============================================================================
LED_ENABLED = True

LED_PIN        = 18    # GPIO 18 — PWM data line to LED strip
LED_COUNT      = 41    # Number of LEDs on the strip
LED_BRIGHTNESS = 128   # 0 (off) to 255 (full brightness)
LED_FREQ_HZ    = 800000
LED_DMA        = 10
LED_INVERT     = False  # True if using NPN transistor level-shifter
LED_CHANNEL    = 0

import threading
import time

# ---------------------------------------------------------------------------
# Hardware init
# ---------------------------------------------------------------------------
_strip = None

if LED_ENABLED:
    try:
        from rpi_ws281x import PixelStrip, Color
        _strip = PixelStrip(
            LED_COUNT, LED_PIN, LED_FREQ_HZ,
            LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL
        )
        _strip.begin()
        print(f"LED strip initialised: {LED_COUNT} LEDs on GPIO {LED_PIN}")
    except Exception as e:
        print(f"LED init failed (running without LEDs): {e}")
        _strip = None

# ---------------------------------------------------------------------------
# Animation thread management
# ---------------------------------------------------------------------------
_stop_event    = threading.Event()
_current_thread = None


def _start_animation(fn):
    """Stop the running animation and start a new one in a daemon thread."""
    global _current_thread
    _stop_event.set()
    if _current_thread and _current_thread.is_alive():
        _current_thread.join(timeout=1.0)
    _stop_event.clear()
    _current_thread = threading.Thread(target=fn, daemon=True)
    _current_thread.start()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _hsv_to_color(h, s=1.0, v=1.0):
    """Convert HSV (h: 0–360, s/v: 0–1) to rpi_ws281x Color."""
    from rpi_ws281x import Color
    h = h % 360
    i = int(h / 60)
    f = (h / 60) - i
    p = v * (1 - s)
    q = v * (1 - s * f)
    t = v * (1 - s * (1 - f))
    r, g, b = [(v, t, p), (q, v, p), (p, v, t),
                (p, q, v), (t, p, v), (v, p, q)][i]
    return Color(int(r * 255), int(g * 255), int(b * 255))


def _all_color(r, g, b):
    """Set every pixel to an RGB colour and push to strip."""
    if _strip is None:
        return
    try:
        from rpi_ws281x import Color
        c = Color(r, g, b)
        for i in range(_strip.numPixels()):
            _strip.setPixelColor(i, c)
        _strip.show()
    except Exception as e:
        print(f"LED error: {e}")


def _all_off():
    _all_color(0, 0, 0)


# ---------------------------------------------------------------------------
# Animation loops (run inside daemon threads)
# ---------------------------------------------------------------------------
def _idle_loop():
    """Slow continuous colour-spectrum fade — all LEDs the same hue."""
    hue = 0.0
    while not _stop_event.is_set():
        if _strip:
            c = _hsv_to_color(hue)
            for i in range(_strip.numPixels()):
                _strip.setPixelColor(i, c)
            _strip.show()
        hue = (hue + 0.5) % 360   # 0.5° per frame → full cycle ~36 s
        _stop_event.wait(0.05)     # ~20 fps


def _pouring_loop():
    """Rainbow cascade — each LED a different hue, rotating fast."""
    base_hue = 0.0
    while not _stop_event.is_set():
        if _strip:
            for i in range(_strip.numPixels()):
                hue = (base_hue + i * (360 / LED_COUNT)) % 360
                _strip.setPixelColor(i, _hsv_to_color(hue))
            _strip.show()
        base_hue = (base_hue + 3) % 360   # 3° per frame → fast spin
        _stop_event.wait(0.03)             # ~33 fps


def _pour_complete_loop():
    """All LEDs flash green for ~7 seconds, then return to idle."""
    deadline = time.time() + 7
    while not _stop_event.is_set() and time.time() < deadline:
        _all_color(0, 255, 0)
        _stop_event.wait(0.3)
        if _stop_event.is_set():
            break
        _all_off()
        _stop_event.wait(0.3)
    _all_off()
    # Return to idle after natural completion (small delay lets this thread exit first)
    if not _stop_event.is_set():
        threading.Timer(0.05, idle).start()


def _error_loop():
    """Fast red flash until another state takes over."""
    while not _stop_event.is_set():
        _all_color(255, 0, 0)
        _stop_event.wait(0.1)
        if _stop_event.is_set():
            break
        _all_off()
        _stop_event.wait(0.1)
    _all_off()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def idle():
    """Slow colour-spectrum fade — bartender waiting for a selection."""
    if not LED_ENABLED or _strip is None:
        return
    _start_animation(_idle_loop)


def pouring():
    """Rainbow cascade — active pour in progress."""
    if not LED_ENABLED or _strip is None:
        return
    _start_animation(_pouring_loop)


def pour_complete():
    """Green flash for ~7 seconds — drink is ready."""
    if not LED_ENABLED or _strip is None:
        return
    _start_animation(_pour_complete_loop)


def error():
    """Fast red flash — low volume warning or pump fault."""
    if not LED_ENABLED or _strip is None:
        return
    _start_animation(_error_loop)


def off():
    """Stop all animations and turn LEDs off immediately."""
    if not LED_ENABLED or _strip is None:
        return
    global _current_thread
    _stop_event.set()
    if _current_thread and _current_thread.is_alive():
        _current_thread.join(timeout=1.0)
    _all_off()


def cleanup():
    """Turn off LEDs and release resources. Call on app exit."""
    if not LED_ENABLED or _strip is None:
        return
    off()
