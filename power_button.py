#!/usr/bin/env python3
"""
Power button for the Smart Bartender Pi — GPIO3, click-pattern controlled.

Runs as its own systemd unit (bartender-power.service), completely separate
from the bartender kiosk app (run.py / kiosk_launch.sh / the desktop
autostart entry). If the app hangs, freezes, or crashes, this is a
different OS process started independently by systemd (PID 1) — the button
keeps working regardless of what the bartender app is doing.

Wiring: a momentary pushbutton between physical pin 5 (GPIO3) and physical
pin 6 (GND). GPIO3 has a permanent ~1.8k pull-up built into the Pi itself,
so no external resistor is needed — pull_up=True below just uses it.

GPIO3 is also the specific pin the Pi's firmware watches to power back on
from a full "poweroff" state — that's a bootloader default on current Pi
firmware, no EEPROM changes needed (same pin, same behavior confirmed
working on the waiver-video-signage project). So the SAME button also
powers the Pi back on after a shutdown, with nothing extra to wire — as
long as mains/USB power was never actually removed. If power was
physically cut, the board just does a normal cold boot when power
returns, no button press needed.

Click patterns:
    3 clicks -> reboot   (systemctl reboot)
    5 clicks -> shutdown (systemctl poweroff)

A sequence is only evaluated once clicking pauses (QUIET_PERIOD of
silence), rather than acting the instant 3 clicks are seen. That's
deliberate: if we acted immediately on the 3rd click, a 5-click shutdown
attempt would always get hijacked into a reboot on its way to 5, since the
3rd click happens before the 5th. Waiting for a pause lets a still-growing
sequence become a 5-click shutdown instead of misfiring as a reboot.

Practical effect of this design: 3 or 4 clicks (with the first 3 landing
within REBOOT_WINDOW) reboots; 5+ clicks (with the first 5 landing within
SHUTDOWN_WINDOW) shuts down; anything else is ignored. So an accidental
4th click doesn't cancel a reboot — only reaching 5 escalates it to a
shutdown. Tighten CLICK checks below if you'd rather require an exact
count.
"""

import subprocess
import time

from gpiozero import Button

PIN = 3

REBOOT_CLICKS = 3
REBOOT_WINDOW = 2.0     # seconds, measured from the 1st click to the 3rd

SHUTDOWN_CLICKS = 5
SHUTDOWN_WINDOW = 3.0   # seconds, measured from the 1st click to the 5th

QUIET_PERIOD = 0.6      # seconds of silence that ends a click sequence
MAX_TRACKED = SHUTDOWN_WINDOW  # never track clicks older than the longest window

BOUNCE_TIME = 0.05      # debounce, matches test_gpio.py's button handling

click_times = []


def evaluate_sequence():
    """Called once clicking has paused. Decide what the sequence meant."""
    global click_times
    if not click_times:
        return

    n = len(click_times)
    first = click_times[0]

    if n >= SHUTDOWN_CLICKS and (click_times[SHUTDOWN_CLICKS - 1] - first) <= SHUTDOWN_WINDOW:
        print(f"[power-button] {n} clicks -> shutdown", flush=True)
        subprocess.run(["systemctl", "poweroff"], check=False)
    elif n >= REBOOT_CLICKS and (click_times[REBOOT_CLICKS - 1] - first) <= REBOOT_WINDOW:
        print(f"[power-button] {n} clicks -> reboot", flush=True)
        subprocess.run(["systemctl", "reboot"], check=False)
    else:
        print(f"[power-button] {n} click(s) - no pattern matched, ignoring", flush=True)

    click_times = []


def on_press():
    now = time.monotonic()
    # Drop anything too old to still be part of this sequence.
    click_times[:] = [t for t in click_times if now - t <= MAX_TRACKED]
    click_times.append(now)
    print(f"[power-button] click {len(click_times)}", flush=True)


def main():
    button = Button(PIN, pull_up=True, bounce_time=BOUNCE_TIME)
    button.when_pressed = on_press

    print("[power-button] watching GPIO3 (pin 5) - ready", flush=True)

    while True:
        time.sleep(QUIET_PERIOD / 2)
        if click_times and (time.monotonic() - click_times[-1]) >= QUIET_PERIOD:
            evaluate_sequence()


if __name__ == "__main__":
    main()
