#!/usr/bin/env python3
"""
LED strip test — run with sudo: sudo python3 test_leds.py
Cycles through red, green, blue (all on), then a pixel wipe, then off.
"""
import time
from rpi_ws281x import PixelStrip, Color

LED_PIN        = 18
LED_COUNT      = 41
LED_BRIGHTNESS = 128
LED_FREQ_HZ    = 800000
LED_DMA        = 10
LED_INVERT     = False
LED_CHANNEL    = 0

strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA,
                   LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()
print(f"Strip initialised: {LED_COUNT} LEDs on GPIO {LED_PIN}")


def all_color(r, g, b, wait=0.5):
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(r, g, b))
    strip.show()
    time.sleep(wait)


def wipe(r, g, b, wait=0.05):
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(r, g, b))
        strip.show()
        time.sleep(wait)


def all_off():
    all_color(0, 0, 0, wait=0)


print("--- Solid colours ---")
print("Red"); all_color(255, 0, 0)
print("Green"); all_color(0, 255, 0)
print("Blue"); all_color(0, 0, 255)
print("White"); all_color(255, 255, 255)

print("--- Wipe ---")
all_off()
wipe(0, 0, 255)   # blue wipe on
wipe(0, 0, 0)     # wipe off

print("--- Done --- turning off")
all_off()
