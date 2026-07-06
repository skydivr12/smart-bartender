# =============================================================================
# LED_ENABLED: set to True when addressable LEDs are physically wired.
# When False, all methods are no-ops — no import errors, no crashes.
# GPIO 18 (PWM) is reserved as the data pin for the LED strip.
# NOTE: rpi_ws281x requires the app to run as root (sudo) on real hardware.
# =============================================================================
LED_ENABLED = False

LED_PIN        = 18    # GPIO 18 — PWM data line to LED strip
LED_COUNT      = 30    # Number of LEDs on the strip — adjust to match yours
LED_BRIGHTNESS = 128   # 0 (off) to 255 (full brightness)
LED_FREQ_HZ    = 800000
LED_DMA        = 10
LED_INVERT     = False  # True if using NPN transistor level-shifter
LED_CHANNEL    = 0


# ---------------------------------------------------------------------------
# Attempt hardware import — only succeeds on a Pi with rpi_ws281x installed
# and LED_ENABLED = True
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
# Helper
# ---------------------------------------------------------------------------
def _all_color(r, g, b):
    """Set every pixel to an RGB colour and show immediately."""
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
# Public behavior methods — called from run.py / pump_manager as needed.
# Fill in light effects here when you're ready; until then they're stubs.
# ---------------------------------------------------------------------------

def idle():
    """
    Ambient state — bartender is waiting for a selection.
    TODO: define effect (e.g. slow colour cycle, soft white pulse).
    """
    if not LED_ENABLED or _strip is None:
        return
    # placeholder — implement effect here
    pass


def pouring():
    """
    Active pour in progress.
    TODO: define effect (e.g. flowing blue animation along the strip).
    """
    if not LED_ENABLED or _strip is None:
        return
    # placeholder — implement effect here
    pass


def pour_complete():
    """
    Pour finished — brief celebration before returning to idle.
    TODO: define effect (e.g. green flash, then fade out).
    """
    if not LED_ENABLED or _strip is None:
        return
    # placeholder — implement effect here
    pass


def error():
    """
    Something went wrong (low volume warning, pump fault, etc.).
    TODO: define effect (e.g. red pulse).
    """
    if not LED_ENABLED or _strip is None:
        return
    # placeholder — implement effect here
    pass


def off():
    """Turn all LEDs off immediately."""
    if not LED_ENABLED or _strip is None:
        return
    _all_off()


def cleanup():
    """Turn off LEDs and release the strip. Call on app exit."""
    if not LED_ENABLED or _strip is None:
        return
    _all_off()
