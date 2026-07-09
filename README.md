# smart-bartender

## Power button

A momentary pushbutton wired between physical pin 5 (GPIO3) and pin 6
(GND) controls power. GPIO3 has a built-in pull-up on the Pi, so no
resistor is needed.

| Action | Pattern |
| --- | --- |
| Reboot | 3 clicks within 2 seconds |
| Safe shutdown | 5 clicks within 3 seconds |
| Power back on after shutdown | 1 click (works as long as power was never physically cut) |

The button is handled by `power_button.py`, running as its own systemd
service (`bartender-power.service`) — completely independent of the
bartender app, so it keeps working even if the app hangs or crashes.
`setup.sh` installs and enables it automatically. GPIO3 wake-from-halt
works out of the box on current Pi firmware, no EEPROM changes needed
(same pin, same behavior confirmed on the waiver-video-signage project).

Logs: `journalctl -u bartender-power -f`