import pygame
import sys
import threading
import time
import os
import socket
import subprocess

# ─────────────────────────────────────────
#  Display settings
# ─────────────────────────────────────────
SCREEN_W = 800
SCREEN_H = 480

# ─────────────────────────────────────────
#  Colours
# ─────────────────────────────────────────
BLACK        = (  0,   0,   0)
WHITE        = (255, 255, 255)
DARK_BG      = ( 18,  18,  18)
CARD_BG      = ( 30,  30,  30)
CARD_HOVER   = ( 45,  45,  45)
ACCENT       = ( 52, 152, 219)
ACCENT_DARK  = ( 31,  97, 141)
GREEN        = ( 46, 204, 113)
RED          = (231,  76,  60)
AMBER        = (243, 156,  18)
GREY         = (127, 140, 141)
TEXT_PRIMARY = (236, 240, 241)
TEXT_SECONDARY=(149, 165, 166)
PIN_EMPTY    = ( 60,  60,  60)
PIN_FILLED   = ( 52, 152, 219)
PIN_ERROR    = (231,  76,  60)

# ─────────────────────────────────────────
#  Layout
# ─────────────────────────────────────────
CARD_MARGIN = 16
CARD_RADIUS = 12
BTN_HEIGHT  = 56
HEADER_H    = 64
FOOTER_H    = 36

# ─────────────────────────────────────────
#  Button GPIO pins
# ─────────────────────────────────────────
BTN_UP     = 5
BTN_DOWN   = 6
BTN_SELECT = 13
BTN_BACK   = 19

SIMULATION = False

try:
    from gpiozero import Button as GPIOButton
    _btn_up     = GPIOButton(BTN_UP,     pull_up=True, bounce_time=0.05)
    _btn_down   = GPIOButton(BTN_DOWN,   pull_up=True, bounce_time=0.05)
    _btn_select = GPIOButton(BTN_SELECT, pull_up=True, bounce_time=0.05)
    _btn_back   = GPIOButton(BTN_BACK,   pull_up=True, bounce_time=0.05)
    GPIO_BUTTONS = {
        'up':     _btn_up,
        'down':   _btn_down,
        'select': _btn_select,
        'back':   _btn_back,
    }
except Exception as e:
    print(f"GPIO buttons not available: {e}")
    GPIO_BUTTONS = {}
    SIMULATION = True


def draw_rounded_rect(surface, colour, rect, radius):
    pygame.draw.rect(surface, colour, rect, border_radius=radius)


def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return float(f.read()) / 1000.0
    except Exception:
        return 0.0


# ─────────────────────────────────────────
#  Base screen
# ─────────────────────────────────────────
class Screen:
    def __init__(self, app):
        self.app = app
        self._hitboxes = []

    def on_enter(self):
        pass

    def handle_input(self, action):
        pass

    def draw(self, surface):
        pass

    # ── Touch support ──────────────────────
    # Screens rebuild self._hitboxes every draw() call: call
    # clear_hitboxes() first, then add_hitbox() next to each rect
    # that's already being drawn. App dispatches raw touch/mouse
    # events to handle_touch(), which hit-tests against this list
    # and reuses the normal handle_input() logic. Purely additive -
    # physical buttons and keyboard keep working unchanged.
    def clear_hitboxes(self):
        self._hitboxes = []

    def add_hitbox(self, rect, callback):
        self._hitboxes.append((rect, callback))

    def handle_touch(self, pos):
        for rect, callback in reversed(self._hitboxes):
            if rect.collidepoint(pos):
                callback()
                return True
        return False

    def draw_header(self, surface, title, show_back=True):
        pygame.draw.rect(surface, CARD_BG,
                         pygame.Rect(0, 0, SCREEN_W, HEADER_H))
        txt = self.app.font_large.render(title, True, TEXT_PRIMARY)
        surface.blit(txt, txt.get_rect(midleft=(20, HEADER_H // 2)))
        if show_back:
            hint = self.app.font_small.render("[ BACK ]", True, TEXT_SECONDARY)
            surface.blit(hint, hint.get_rect(
                midright=(SCREEN_W - 20, HEADER_H // 2)))
            # generous tap target - the whole right side of the header
            self.add_hitbox(
                pygame.Rect(SCREEN_W - 170, 0, 170, HEADER_H),
                lambda: self.handle_input('back'))

    def draw_footer(self, surface):
        """Persistent footer showing web address and temperature."""
        pygame.draw.rect(surface, CARD_BG,
                         pygame.Rect(0, SCREEN_H - FOOTER_H,
                                     SCREEN_W, FOOTER_H))
        # web address
        web = self.app.font_small.render(
            f"http://bartender.local:5000", True, ACCENT)
        surface.blit(web, web.get_rect(
            midleft=(16, SCREEN_H - FOOTER_H // 2)))
        # temperature
        temp = get_cpu_temp()
        temp_col = RED if temp > 65 else AMBER if temp > 55 else TEXT_SECONDARY
        temp_txt = self.app.font_small.render(
            f"CPU {temp:.0f}°C", True, temp_col)
        surface.blit(temp_txt, temp_txt.get_rect(
            midright=(SCREEN_W - 16, SCREEN_H - FOOTER_H // 2)))

    def draw_nav_hint(self, surface):
        hint = self.app.font_small.render(
            "▲ ▼  scroll       ● select       ✕ back",
            True, GREY)
        surface.blit(hint, hint.get_rect(
            midbottom=(SCREEN_W // 2, SCREEN_H - FOOTER_H - 4)))


# ─────────────────────────────────────────
#  PIN Entry screen
# ─────────────────────────────────────────
class PinScreen(Screen):
    """
    4-digit PIN entry.
    UP/DOWN change the current digit.
    SELECT confirms a digit and moves to next.
    BACK cancels and returns to drinks.
    On success, navigates to self.destination.
    """
    def __init__(self, app):
        super().__init__(app)
        self.digits      = [0, 0, 0, 0]
        self.position    = 0
        self.error       = False
        self.destination = 'config'

    def on_enter(self):
        self.digits   = [0, 0, 0, 0]
        self.position = 0
        self.error    = False

    def handle_input(self, action):
        if action == 'back':
            self.app.set_screen('drinks')
            return
        if action == 'up':
            self.digits[self.position] = \
                (self.digits[self.position] + 1) % 10
            self.error = False
        elif action == 'down':
            self.digits[self.position] = \
                (self.digits[self.position] - 1) % 10
            self.error = False
        elif action == 'select':
            if self.position < 3:
                self.position += 1
            else:
                # all 4 digits entered - check PIN
                entered = ''.join(str(d) for d in self.digits)
                if self.app.settings.check_pin(entered):
                    self.app.set_screen(self.destination)
                else:
                    self.error    = True
                    self.digits   = [0, 0, 0, 0]
                    self.position = 0

    def draw(self, surface):
        surface.fill(DARK_BG)
        self.draw_header(surface, "Enter PIN", show_back=True)

        # instruction
        inst = self.app.font_small.render(
            "▲ ▼ change digit        ● confirm digit", True, TEXT_SECONDARY)
        surface.blit(inst, inst.get_rect(center=(SCREEN_W // 2, 130)))

        # PIN dots
        dot_size  = 60
        dot_gap   = 24
        total_w   = 4 * dot_size + 3 * dot_gap
        start_x   = (SCREEN_W - total_w) // 2
        y         = 180

        for i in range(4):
            x      = start_x + i * (dot_size + dot_gap)
            rect   = pygame.Rect(x, y, dot_size, dot_size)
            active = (i == self.position)

            if self.error:
                colour = PIN_ERROR
            elif i < self.position:
                colour = PIN_FILLED
            elif active:
                colour = ACCENT
            else:
                colour = PIN_EMPTY

            draw_rounded_rect(surface, colour, rect, 12)

            # show digit for current position, dot for others
            if active or self.error:
                d = self.app.font_large.render(
                    str(self.digits[i]), True, WHITE)
            else:
                d = self.app.font_large.render(
                    "●" if i < self.position else "–", True, WHITE)
            surface.blit(d, d.get_rect(center=rect.center))

        if self.error:
            err = self.app.font_large.render(
                "Incorrect PIN — try again", True, PIN_ERROR)
            surface.blit(err, err.get_rect(center=(SCREEN_W // 2, 290)))
        else:
            pos_hint = self.app.font_small.render(
                f"Digit {self.position + 1} of 4", True, GREY)
            surface.blit(pos_hint, pos_hint.get_rect(
                center=(SCREEN_W // 2, 290)))

        self.draw_footer(surface)


# ─────────────────────────────────────────
#  Drink select screen
# ─────────────────────────────────────────
class DrinkSelectScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.drinks        = []
        self.index         = 0
        self.scroll_off    = 0
        self.cards_visible = 4

    def on_enter(self):
        available     = self.app.pump_manager.get_available_ingredients()
        self.drinks   = self.app.drink_manager.get_available_drinks(available)
        self.index    = 0
        self.scroll_off = 0

    def handle_input(self, action):
        if not self.drinks:
            if action == 'select':
                self.app.pin_screen.destination = 'config'
                self.app.set_screen('pin')
            return

        if action == 'up':
            self.index = (self.index - 1) % (len(self.drinks) + 1)
        elif action == 'down':
            self.index = (self.index + 1) % (len(self.drinks) + 1)
        elif action == 'select':
            if self.index == len(self.drinks):
                # Settings button selected
                self.app.pin_screen.destination = 'config'
                self.app.set_screen('pin')
            else:
                self.app.selected_drink = self.drinks[self.index]
                self.app.set_screen('size')
        elif action == 'back':
            pass  # already on main screen

        # scrolling
        if self.index < self.scroll_off:
            self.scroll_off = self.index
        elif self.index >= self.scroll_off + self.cards_visible:
            self.scroll_off = self.index - self.cards_visible + 1

    def _tap_drink(self, i):
        self.index = i
        self.handle_input('select')

    def draw(self, surface):
        surface.fill(DARK_BG)
        self.clear_hitboxes()
        self.draw_header(surface, "🍹  Smart Bartender", show_back=False)

        if not self.drinks:
            msg  = self.app.font_large.render(
                "No drinks available", True, TEXT_SECONDARY)
            msg2 = self.app.font_small.render(
                "Configure pumps first  →  press SELECT", True, GREY)
            surface.blit(msg,  msg.get_rect(center=(SCREEN_W // 2, 200)))
            surface.blit(msg2, msg2.get_rect(center=(SCREEN_W // 2, 245)))
            self.add_hitbox(
                pygame.Rect(0, HEADER_H, SCREEN_W,
                            SCREEN_H - HEADER_H - FOOTER_H),
                lambda: self.handle_input('select'))
            self.draw_footer(surface)
            return

        content_h  = SCREEN_H - HEADER_H - FOOTER_H - 40
        card_h     = content_h // self.cards_visible
        y          = HEADER_H + CARD_MARGIN

        # total items = drinks + settings button
        total_items = len(self.drinks) + 1
        visible_drinks = self.drinks[self.scroll_off:
                                     self.scroll_off + self.cards_visible]

        for i, drink in enumerate(visible_drinks):
            actual_i  = self.scroll_off + i
            ing_names = ", ".join(drink["ingredients"].keys())
            selected  = (actual_i == self.index)
            bg        = CARD_HOVER if selected else CARD_BG
            rect      = pygame.Rect(CARD_MARGIN, y,
                                    SCREEN_W - CARD_MARGIN * 2, card_h - 6)
            draw_rounded_rect(surface, bg, rect, CARD_RADIUS)
            if selected:
                pygame.draw.rect(surface, ACCENT,
                                 pygame.Rect(CARD_MARGIN, y + 8,
                                             5, card_h - 22),
                                 border_radius=3)
            lbl = self.app.font_large.render(drink["name"], True, TEXT_PRIMARY)
            sub = self.app.font_small.render(ing_names, True, TEXT_SECONDARY)
            surface.blit(lbl, lbl.get_rect(
                midleft=(CARD_MARGIN + 20, y + card_h // 2 - 10)))
            surface.blit(sub, sub.get_rect(
                midleft=(CARD_MARGIN + 20, y + card_h // 2 + 12)))
            self.add_hitbox(rect, lambda i=actual_i: self._tap_drink(i))
            y += card_h

        # Settings button at bottom of list
        settings_i = len(self.drinks)
        if settings_i >= self.scroll_off and \
           settings_i < self.scroll_off + self.cards_visible:
            selected = (self.index == settings_i)
            bg       = CARD_HOVER if selected else CARD_BG
            rect     = pygame.Rect(CARD_MARGIN, y,
                                   SCREEN_W - CARD_MARGIN * 2, card_h - 6)
            draw_rounded_rect(surface, bg, rect, CARD_RADIUS)
            if selected:
                pygame.draw.rect(surface, AMBER,
                                 pygame.Rect(CARD_MARGIN, y + 8,
                                             5, card_h - 22),
                                 border_radius=3)
            lbl = self.app.font_large.render(
                "⚙  Settings", True,
                AMBER if selected else TEXT_SECONDARY)
            surface.blit(lbl, lbl.get_rect(
                midleft=(CARD_MARGIN + 20, y + (card_h - 6) // 2)))
            self.add_hitbox(rect, lambda i=settings_i: self._tap_drink(i))

        # scroll indicator
        if total_items > self.cards_visible:
            bar_h   = SCREEN_H - HEADER_H - FOOTER_H - 40
            thumb_h = max(30, bar_h * self.cards_visible // total_items)
            thumb_y = HEADER_H + (bar_h - thumb_h) * \
                      self.scroll_off // max(1, total_items - self.cards_visible)
            pygame.draw.rect(surface, GREY,
                             (SCREEN_W - 6, HEADER_H, 4, bar_h),
                             border_radius=2)
            pygame.draw.rect(surface, ACCENT,
                             (SCREEN_W - 6, thumb_y, 4, thumb_h),
                             border_radius=2)

        self.draw_nav_hint(surface)
        self.draw_footer(surface)


# ─────────────────────────────────────────
#  Size / Strength screen
# ─────────────────────────────────────────
class SizeStrengthScreen(Screen):
    SIZES     = ["Small", "Regular", "Large"]
    STRENGTHS = ["Normal", "Double"]

    def __init__(self, app):
        super().__init__(app)
        self.size_idx     = 1
        self.strength_idx = 0
        self.row          = 0

    def on_enter(self):
        self.size_idx     = 1
        self.strength_idx = 0
        self.row          = 0

    def handle_input(self, action):
        if action == 'up':
            self.row = (self.row - 1) % 3
        elif action == 'down':
            self.row = (self.row + 1) % 3
        elif action == 'back':
            self.app.set_screen('drinks')
        elif action == 'select':
            if self.row == 0:
                self.size_idx = (self.size_idx + 1) % len(self.SIZES)
            elif self.row == 1:
                self.strength_idx = \
                    (self.strength_idx + 1) % len(self.STRENGTHS)
            elif self.row == 2:
                self._pour()

    def _pour(self):
        drink    = self.app.selected_drink
        size     = self.SIZES[self.size_idx]
        strength = self.STRENGTHS[self.strength_idx]
        scaled   = self.app.drink_manager.scale_ingredients(
            drink["ingredients"], size=size, strength=strength)
        self.app.pour_ingredients = scaled
        self.app.pour_drink_name  = drink["name"]
        self.app.set_screen('pouring')

    def _tap_row(self, i):
        self.row = i
        self.handle_input('select')

    def draw(self, surface):
        surface.fill(DARK_BG)
        self.clear_hitboxes()
        drink = self.app.selected_drink
        self.draw_header(surface, drink["name"] if drink else "")

        rows = [
            ("Size",     self.SIZES[self.size_idx]),
            ("Strength", self.STRENGTHS[self.strength_idx]),
        ]

        y = HEADER_H + 30
        for i, (label, value) in enumerate(rows):
            selected = (self.row == i)
            bg       = CARD_HOVER if selected else CARD_BG
            rect     = pygame.Rect(CARD_MARGIN, y,
                                   SCREEN_W - CARD_MARGIN * 2, BTN_HEIGHT)
            draw_rounded_rect(surface, bg, rect, CARD_RADIUS)
            if selected:
                pygame.draw.rect(surface, ACCENT,
                                 pygame.Rect(CARD_MARGIN, y + 8,
                                             5, BTN_HEIGHT - 16),
                                 border_radius=3)
            lbl = self.app.font_small.render(label, True, TEXT_SECONDARY)
            val = self.app.font_large.render(value, True, TEXT_PRIMARY)
            surface.blit(lbl, lbl.get_rect(
                midleft=(CARD_MARGIN + 20, y + BTN_HEIGHT // 2 - 10)))
            surface.blit(val, val.get_rect(
                midleft=(CARD_MARGIN + 20, y + BTN_HEIGHT // 2 + 12)))
            if selected:
                hint = self.app.font_small.render(
                    "← SELECT to change →", True, ACCENT)
                surface.blit(hint, hint.get_rect(
                    midright=(SCREEN_W - CARD_MARGIN - 10,
                              y + BTN_HEIGHT // 2)))
            self.add_hitbox(rect, lambda i=i: self._tap_row(i))
            y += BTN_HEIGHT + 10

        y += 10
        pour_rect = pygame.Rect(CARD_MARGIN, y,
                                SCREEN_W - CARD_MARGIN * 2, BTN_HEIGHT + 10)
        colour = ACCENT if self.row == 2 else ACCENT_DARK
        draw_rounded_rect(surface, colour, pour_rect, CARD_RADIUS)
        pour_lbl = self.app.font_large.render("POUR DRINK", True, WHITE)
        surface.blit(pour_lbl, pour_lbl.get_rect(center=pour_rect.center))
        self.add_hitbox(pour_rect, lambda: self._tap_row(2))

        self.draw_nav_hint(surface)
        self.draw_footer(surface)


# ─────────────────────────────────────────
#  Pouring screen
# ─────────────────────────────────────────
class PouringScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.progress = 0
        self.done     = False
        self.warnings = []

    def on_enter(self):
        self.progress = 0
        self.done     = False
        self.warnings = []

        def on_progress(pct):
            self.progress = pct

        def on_complete():
            self.done     = True
            low           = self.app.pump_manager.get_low_pumps()
            self.warnings = [f"{p.name} ({p.value}) is low!" for p in low]
            pygame.time.set_timer(pygame.USEREVENT + 1, 3000)

        self.app.pump_manager.make_drink(
            self.app.pour_ingredients,
            on_progress=on_progress,
            on_complete=on_complete
        )

    def handle_input(self, action):
        if self.done and action in ('select', 'back'):
            self.app.set_screen('drinks')

    def draw(self, surface):
        surface.fill(DARK_BG)
        self.clear_hitboxes()
        name = self.app.pour_drink_name or "Drink"
        self.draw_header(surface, f"Pouring  {name}...", show_back=False)

        bar_x  = CARD_MARGIN * 3
        bar_y  = 200
        bar_w  = SCREEN_W - CARD_MARGIN * 6
        bar_h  = 32
        pygame.draw.rect(surface, CARD_BG,
                         (bar_x, bar_y, bar_w, bar_h), border_radius=8)
        fill_w = int(bar_w * self.progress / 100)
        if fill_w > 0:
            colour = GREEN if self.done else ACCENT
            pygame.draw.rect(surface, colour,
                             (bar_x, bar_y, fill_w, bar_h), border_radius=8)

        pct_txt = self.app.font_large.render(
            f"{self.progress}%", True, TEXT_PRIMARY)
        surface.blit(pct_txt, pct_txt.get_rect(center=(SCREEN_W // 2, 270)))

        if self.done:
            done_txt = self.app.font_large.render(
                "Enjoy your drink! 🎉", True, GREEN)
            surface.blit(done_txt,
                         done_txt.get_rect(center=(SCREEN_W // 2, 320)))
            for i, w in enumerate(self.warnings):
                warn = self.app.font_small.render(f"⚠  {w}", True, AMBER)
                surface.blit(warn, warn.get_rect(
                    center=(SCREEN_W // 2, 370 + i * 24)))
            hint = self.app.font_small.render(
                "Press SELECT to return to menu", True, GREY)
            surface.blit(hint, hint.get_rect(
                midbottom=(SCREEN_W // 2, SCREEN_H - FOOTER_H - 10)))
            self.add_hitbox(
                pygame.Rect(0, HEADER_H, SCREEN_W,
                            SCREEN_H - HEADER_H - FOOTER_H),
                lambda: self.handle_input('select'))

        self.draw_footer(surface)


# ─────────────────────────────────────────
#  Config / main settings menu
# ─────────────────────────────────────────
class ConfigScreen(Screen):
    OPTIONS = [
        "Configure Pumps",
        "Clean All Pumps",
        "Prime a Pump",
        "Add Custom Drink",
        "Change PIN",
        "WiFi Settings",
        "Back to Drinks",
    ]

    def __init__(self, app):
        super().__init__(app)
        self.index = 0

    def on_enter(self):
        self.index = 0

    def handle_input(self, action):
        if action == 'up':
            self.index = (self.index - 1) % len(self.OPTIONS)
        elif action == 'down':
            self.index = (self.index + 1) % len(self.OPTIONS)
        elif action == 'back':
            self.app.set_screen('drinks')
        elif action == 'select':
            choice = self.OPTIONS[self.index]
            if choice == "Configure Pumps":
                self.app.set_screen('pumps')
            elif choice == "Clean All Pumps":
                self.app.set_screen('cleaning')
            elif choice == "Prime a Pump":
                self.app.set_screen('prime')
            elif choice == "Add Custom Drink":
                self.app.set_screen('custom')
            elif choice == "Change PIN":
                self.app.set_screen('change_pin')
            elif choice == "WiFi Settings":
                self.app.set_screen('wifi')
            elif choice == "Back to Drinks":
                self.app.set_screen('drinks')

    def _tap_option(self, i):
        self.index = i
        self.handle_input('select')

    def draw(self, surface):
        surface.fill(DARK_BG)
        self.clear_hitboxes()
        self.draw_header(surface, "Settings")

        y      = HEADER_H + CARD_MARGIN
        card_h = 52

        for i, opt in enumerate(self.OPTIONS):
            selected = (i == self.index)
            bg       = CARD_HOVER if selected else CARD_BG
            rect     = pygame.Rect(CARD_MARGIN, y,
                                   SCREEN_W - CARD_MARGIN * 2, card_h - 4)
            draw_rounded_rect(surface, bg, rect, CARD_RADIUS)
            if selected:
                pygame.draw.rect(surface, ACCENT,
                                 pygame.Rect(CARD_MARGIN, y + 6,
                                             5, card_h - 16),
                                 border_radius=3)
            lbl = self.app.font_large.render(opt, True, TEXT_PRIMARY)
            surface.blit(lbl, lbl.get_rect(
                midleft=(CARD_MARGIN + 20, y + (card_h - 4) // 2)))
            self.add_hitbox(rect, lambda i=i: self._tap_option(i))
            y += card_h

        self.draw_nav_hint(surface)
        self.draw_footer(surface)


# ─────────────────────────────────────────
#  Pump config screen
# ─────────────────────────────────────────
class PumpConfigScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.pump_keys = []
        self.index     = 0
        self.editing   = None
        self.edit_row  = 0
        self.volumes   = [0, 50, 100, 200, 375, 500, 750, 1000, 1750]
        self.vol_idx   = 0
        from drinks import DRINK_OPTIONS
        self.options = [{"name": "Empty", "value": None}] + DRINK_OPTIONS
        self.opt_idx = 0

    def on_enter(self):
        self.pump_keys = sorted(self.app.pump_manager.pumps.keys())
        self.index     = 0
        self.editing   = None

    def _current_pump(self):
        if not self.pump_keys:
            return None
        return self.app.pump_manager.pumps[self.pump_keys[self.index]]

    def _start_editing(self):
        pump = self._current_pump()
        if not pump:
            return
        self.editing  = pump.key
        self.edit_row = 0
        self.opt_idx  = 0
        for i, opt in enumerate(self.options):
            if opt["value"] == pump.value:
                self.opt_idx = i
                break
        self.vol_idx = 0
        for i, v in enumerate(self.volumes):
            if v == pump.volume_ml:
                self.vol_idx = i
                break

    def _save_edit(self):
        pump           = self.app.pump_manager.pumps[self.editing]
        pump.value     = self.options[self.opt_idx]["value"]
        pump.volume_ml = self.volumes[self.vol_idx]
        self.app.pump_manager.save()
        self.editing   = None

    def handle_input(self, action):
        if self.editing is None:
            if action == 'up':
                self.index = (self.index - 1) % len(self.pump_keys)
            elif action == 'down':
                self.index = (self.index + 1) % len(self.pump_keys)
            elif action == 'select':
                self._start_editing()
            elif action == 'back':
                self.app.set_screen('config')
        else:
            if action == 'back':
                self.editing = None
            elif action == 'up':
                self.edit_row = (self.edit_row - 1) % 3
            elif action == 'down':
                self.edit_row = (self.edit_row + 1) % 3
            elif action == 'select':
                if self.edit_row == 0:
                    self.opt_idx = (self.opt_idx + 1) % len(self.options)
                elif self.edit_row == 1:
                    self.vol_idx = (self.vol_idx + 1) % len(self.volumes)
                elif self.edit_row == 2:
                    self._save_edit()

    def _tap_pump_row(self, i):
        self.index = i
        self.handle_input('select')

    def _tap_edit_row(self, i):
        self.edit_row = i
        self.handle_input('select')

    def draw(self, surface):
        surface.fill(DARK_BG)
        self.clear_hitboxes()
        self.draw_header(surface, "Configure Pumps")
        if self.editing:
            self._draw_edit(surface)
        else:
            self._draw_list(surface)
        self.draw_nav_hint(surface)
        self.draw_footer(surface)

    def _draw_list(self, surface):
        y             = HEADER_H + CARD_MARGIN
        card_h        = 54
        visible_count = 5
        scroll        = max(0, self.index - visible_count + 1)

        for i, key in enumerate(self.pump_keys[scroll:scroll + visible_count]):
            actual_i = scroll + i
            pump     = self.app.pump_manager.pumps[key]
            selected = (actual_i == self.index)
            bg       = CARD_HOVER if selected else CARD_BG
            rect     = pygame.Rect(CARD_MARGIN, y,
                                   SCREEN_W - CARD_MARGIN * 2, card_h - 4)
            draw_rounded_rect(surface, bg, rect, CARD_RADIUS)
            if selected:
                pygame.draw.rect(surface, ACCENT,
                                 pygame.Rect(CARD_MARGIN, y + 6,
                                             5, card_h - 16),
                                 border_radius=3)
            name_txt = self.app.font_large.render(
                pump.name, True, TEXT_PRIMARY)
            surface.blit(name_txt, name_txt.get_rect(
                midleft=(CARD_MARGIN + 20, y + (card_h - 4) // 2 - 8)))
            liquid = pump.value if pump.value else "Empty"
            sub    = self.app.font_small.render(
                f"{liquid}  ·  {pump.volume_ml}ml", True,
                AMBER if pump.is_low() else TEXT_SECONDARY)
            surface.blit(sub, sub.get_rect(
                midleft=(CARD_MARGIN + 20, y + (card_h - 4) // 2 + 10)))
            if pump.is_low():
                warn = self.app.font_small.render("LOW", True, AMBER)
                surface.blit(warn, warn.get_rect(
                    midright=(SCREEN_W - CARD_MARGIN - 10,
                              y + (card_h - 4) // 2)))
            self.add_hitbox(rect, lambda i=actual_i: self._tap_pump_row(i))
            y += card_h

    def _draw_edit(self, surface):
        pump  = self.app.pump_manager.pumps[self.editing]
        title = self.app.font_large.render(
            f"Editing  {pump.name}", True, ACCENT)
        surface.blit(title, title.get_rect(
            midleft=(CARD_MARGIN, HEADER_H + 20)))

        rows = [
            ("Liquid", self.options[self.opt_idx]["name"]),
            ("Volume", f"{self.volumes[self.vol_idx]} ml"),
            ("",       "SAVE"),
        ]

        y = HEADER_H + 60
        for i, (label, value) in enumerate(rows):
            selected = (i == self.edit_row)
            is_save  = (i == 2)
            bg       = ACCENT if (selected and is_save) else \
                       CARD_HOVER if selected else CARD_BG
            rect     = pygame.Rect(CARD_MARGIN, y,
                                   SCREEN_W - CARD_MARGIN * 2, BTN_HEIGHT)
            draw_rounded_rect(surface, bg, rect, CARD_RADIUS)
            if selected and not is_save:
                pygame.draw.rect(surface, ACCENT,
                                 pygame.Rect(CARD_MARGIN, y + 8,
                                             5, BTN_HEIGHT - 16),
                                 border_radius=3)
            if label:
                lbl = self.app.font_small.render(label, True, TEXT_SECONDARY)
                surface.blit(lbl, lbl.get_rect(
                    midleft=(CARD_MARGIN + 20, y + BTN_HEIGHT // 2 - 10)))
            val_col = WHITE if (selected and is_save) else TEXT_PRIMARY
            val     = self.app.font_large.render(value, True, val_col)
            surface.blit(val, val.get_rect(
                center=rect.center if is_save else None,
                midleft=None if is_save else (
                    CARD_MARGIN + 20, y + BTN_HEIGHT // 2 + 10)))
            if selected and not is_save:
                hint = self.app.font_small.render(
                    "← SELECT to cycle →", True, ACCENT)
                surface.blit(hint, hint.get_rect(
                    midright=(SCREEN_W - CARD_MARGIN - 10,
                              y + BTN_HEIGHT // 2)))
            self.add_hitbox(rect, lambda i=i: self._tap_edit_row(i))
            y += BTN_HEIGHT + 10


# ─────────────────────────────────────────
#  Prime screen
# ─────────────────────────────────────────
class PrimeScreen(Screen):
    """Run a single pump until the user stops it."""
    def __init__(self, app):
        super().__init__(app)
        self.pump_keys  = []
        self.index      = 0
        self.priming    = False
        self.start_time = None
        self._thread    = None

    def on_enter(self):
        self.pump_keys = sorted(self.app.pump_manager.pumps.keys())
        self.index     = 0
        self.priming   = False
        self.start_time= None

    def _current_pump(self):
        return self.app.pump_manager.pumps[self.pump_keys[self.index]]

    def handle_input(self, action):
        if self.priming:
            if action in ('select', 'back'):
                self._stop()
            return

        if action == 'up':
            self.index = (self.index - 1) % len(self.pump_keys)
        elif action == 'down':
            self.index = (self.index + 1) % len(self.pump_keys)
        elif action == 'select':
            self._start()
        elif action == 'back':
            self.app.set_screen('config')

    def _start(self):
        pump = self._current_pump()
        if not pump._device:
            return
        self.priming    = True
        self.start_time = time.time()
        pump._device.on()

    def _stop(self):
        pump = self._current_pump()
        if pump._device:
            pump._device.off()
        self.priming = False

    def _tap_pump_row(self, i):
        self.index = i
        self.handle_input('select')

    def draw(self, surface):
        surface.fill(DARK_BG)
        self.clear_hitboxes()
        self.draw_header(surface, "Prime Pump")

        if not self.priming:
            # pump selector
            y      = HEADER_H + CARD_MARGIN
            card_h = 54
            for i, key in enumerate(self.pump_keys):
                pump     = self.app.pump_manager.pumps[key]
                selected = (i == self.index)
                bg       = CARD_HOVER if selected else CARD_BG
                rect     = pygame.Rect(CARD_MARGIN, y,
                                       SCREEN_W - CARD_MARGIN * 2, card_h - 4)
                draw_rounded_rect(surface, bg, rect, CARD_RADIUS)
                if selected:
                    pygame.draw.rect(surface, ACCENT,
                                     pygame.Rect(CARD_MARGIN, y + 6,
                                                 5, card_h - 16),
                                     border_radius=3)
                lbl = self.app.font_large.render(pump.name, True, TEXT_PRIMARY)
                sub = self.app.font_small.render(
                    pump.value if pump.value else "Empty",
                    True, TEXT_SECONDARY)
                surface.blit(lbl, lbl.get_rect(
                    midleft=(CARD_MARGIN + 20, y + (card_h-4)//2 - 8)))
                surface.blit(sub, sub.get_rect(
                    midleft=(CARD_MARGIN + 20, y + (card_h-4)//2 + 10)))
                self.add_hitbox(rect, lambda i=i: self._tap_pump_row(i))
                y += card_h

            inst = self.app.font_small.render(
                "SELECT to start priming  ·  BACK to cancel",
                True, GREY)
            surface.blit(inst, inst.get_rect(
                midbottom=(SCREEN_W//2, SCREEN_H - FOOTER_H - 10)))
        else:
            pump    = self._current_pump()
            elapsed = time.time() - self.start_time
            msg     = self.app.font_large.render(
                f"Priming  {pump.name}...", True, ACCENT)
            liq     = self.app.font_small.render(
                pump.value if pump.value else "No liquid set",
                True, TEXT_SECONDARY)
            secs    = self.app.font_large.render(
                f"{elapsed:.1f}s", True, GREEN)
            stop    = self.app.font_large.render(
                "Press SELECT or BACK to stop", True, AMBER)
            surface.blit(msg,  msg.get_rect(center=(SCREEN_W//2, 180)))
            surface.blit(liq,  liq.get_rect(center=(SCREEN_W//2, 225)))
            surface.blit(secs, secs.get_rect(center=(SCREEN_W//2, 290)))
            surface.blit(stop, stop.get_rect(center=(SCREEN_W//2, 360)))
            self.add_hitbox(
                pygame.Rect(0, HEADER_H, SCREEN_W,
                            SCREEN_H - HEADER_H - FOOTER_H),
                lambda: self.handle_input('select'))

        self.draw_footer(surface)


# ─────────────────────────────────────────
#  Cleaning screen
# ─────────────────────────────────────────
class CleaningScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.progress = 0
        self.done     = False
        self.started  = False

    def on_enter(self):
        self.progress = 0
        self.done     = False
        self.started  = False

    def handle_input(self, action):
        if not self.started and action == 'select':
            self._start_clean()
        elif not self.started and action == 'back':
            self.app.set_screen('config')
        elif self.done and action in ('select', 'back'):
            self.app.set_screen('config')

    def _start_clean(self):
        self.started = True

        def on_progress(pct):
            self.progress = pct

        def on_complete():
            self.done = True

        self.app.pump_manager.clean_all(
            on_progress=on_progress,
            on_complete=on_complete)

    def draw(self, surface):
        surface.fill(DARK_BG)
        self.clear_hitboxes()
        self.draw_header(surface, "Clean All Pumps")

        if not self.started:
            msg  = self.app.font_large.render(
                "Hook tubes up to water first.", True, TEXT_PRIMARY)
            msg2 = self.app.font_small.render(
                "All pumps will run for 20 seconds.",
                True, TEXT_SECONDARY)
            msg3 = self.app.font_small.render(
                "SELECT to start  ·  BACK to cancel", True, GREY)
            surface.blit(msg,  msg.get_rect(center=(SCREEN_W//2, 200)))
            surface.blit(msg2, msg2.get_rect(center=(SCREEN_W//2, 245)))
            surface.blit(msg3, msg3.get_rect(center=(SCREEN_W//2, 290)))
            self.add_hitbox(
                pygame.Rect(0, HEADER_H, SCREEN_W,
                            SCREEN_H - HEADER_H - FOOTER_H),
                lambda: self.handle_input('select'))
        else:
            bar_x  = CARD_MARGIN * 3
            bar_y  = 200
            bar_w  = SCREEN_W - CARD_MARGIN * 6
            bar_h  = 32
            pygame.draw.rect(surface, CARD_BG,
                             (bar_x, bar_y, bar_w, bar_h), border_radius=8)
            fill_w = int(bar_w * self.progress / 100)
            if fill_w > 0:
                colour = GREEN if self.done else ACCENT
                pygame.draw.rect(surface, colour,
                                 (bar_x, bar_y, fill_w, bar_h),
                                 border_radius=8)
            pct = self.app.font_large.render(
                f"{self.progress}%", True, TEXT_PRIMARY)
            surface.blit(pct, pct.get_rect(center=(SCREEN_W//2, 260)))
            if self.done:
                done = self.app.font_large.render(
                    "Cleaning complete!", True, GREEN)
                surface.blit(done, done.get_rect(center=(SCREEN_W//2, 320)))
                hint = self.app.font_small.render(
                    "Press SELECT to return", True, GREY)
                surface.blit(hint, hint.get_rect(
                    midbottom=(SCREEN_W//2, SCREEN_H - FOOTER_H - 10)))
                self.add_hitbox(
                    pygame.Rect(0, HEADER_H, SCREEN_W,
                                SCREEN_H - HEADER_H - FOOTER_H),
                    lambda: self.handle_input('select'))

        self.draw_footer(surface)


# ─────────────────────────────────────────
#  Change PIN screen
# ─────────────────────────────────────────
class ChangePinScreen(Screen):
    """Enter a new 4-digit PIN twice to confirm."""
    def __init__(self, app):
        super().__init__(app)
        self.stage    = 'new'    # 'new' or 'confirm'
        self.first    = []
        self.digits   = [0, 0, 0, 0]
        self.position = 0
        self.error    = False
        self.success  = False

    def on_enter(self):
        self.stage    = 'new'
        self.first    = []
        self.digits   = [0, 0, 0, 0]
        self.position = 0
        self.error    = False
        self.success  = False

    def handle_input(self, action):
        if self.success:
            if action in ('select', 'back'):
                self.app.set_screen('config')
            return
        if action == 'back':
            if self.stage == 'confirm':
                self.stage    = 'new'
                self.digits   = [0, 0, 0, 0]
                self.position = 0
                self.error    = False
            else:
                self.app.set_screen('config')
            return
        if action == 'up':
            self.digits[self.position] = \
                (self.digits[self.position] + 1) % 10
            self.error = False
        elif action == 'down':
            self.digits[self.position] = \
                (self.digits[self.position] - 1) % 10
            self.error = False
        elif action == 'select':
            if self.position < 3:
                self.position += 1
            else:
                entered = ''.join(str(d) for d in self.digits)
                if self.stage == 'new':
                    self.first    = entered
                    self.stage    = 'confirm'
                    self.digits   = [0, 0, 0, 0]
                    self.position = 0
                else:
                    if entered == self.first:
                        self.app.settings.set_pin(entered)
                        self.success = True
                    else:
                        self.error    = True
                        self.digits   = [0, 0, 0, 0]
                        self.position = 0

    def draw(self, surface):
        surface.fill(DARK_BG)
        title = "Confirm New PIN" if self.stage == 'confirm' else "Enter New PIN"
        self.draw_header(surface, title)

        if self.success:
            msg = self.app.font_large.render("PIN changed!", True, GREEN)
            surface.blit(msg, msg.get_rect(center=(SCREEN_W//2, 240)))
            self.draw_footer(surface)
            return

        inst = self.app.font_small.render(
            "▲ ▼ change digit        ● confirm digit",
            True, TEXT_SECONDARY)
        surface.blit(inst, inst.get_rect(center=(SCREEN_W//2, 130)))

        dot_size = 60
        dot_gap  = 24
        total_w  = 4 * dot_size + 3 * dot_gap
        start_x  = (SCREEN_W - total_w) // 2
        y        = 180

        for i in range(4):
            x      = start_x + i * (dot_size + dot_gap)
            rect   = pygame.Rect(x, y, dot_size, dot_size)
            active = (i == self.position)
            colour = PIN_ERROR if self.error else \
                     PIN_FILLED if i < self.position else \
                     ACCENT if active else PIN_EMPTY
            draw_rounded_rect(surface, colour, rect, 12)
            d = self.app.font_large.render(
                str(self.digits[i]) if active else
                "●" if i < self.position else "–",
                True, WHITE)
            surface.blit(d, d.get_rect(center=rect.center))

        if self.error:
            err = self.app.font_large.render(
                "PINs don't match — try again", True, PIN_ERROR)
            surface.blit(err, err.get_rect(center=(SCREEN_W//2, 290)))

        self.draw_footer(surface)


# ─────────────────────────────────────────
#  WiFi settings screen
# ─────────────────────────────────────────
class WifiScreen(Screen):
    """
    Scans for networks and lets the user connect.
    SSID is selected from a list.
    Password is entered character by character using
    UP/DOWN to cycle characters, SELECT to confirm each,
    BACK to delete last character.
    """
    CHARS = (" abcdefghijklmnopqrstuvwxyz"
             "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
             "0123456789!@#$%^&*()-_=+[]{}|;:',.<>?/`~")

    def __init__(self, app):
        super().__init__(app)
        self.stage      = 'scan'   # scan, select, password, connecting, done
        self.networks   = []
        self.net_index  = 0
        self.password   = []
        self.char_index = 0
        self.message    = ""
        self.scanning   = False

    def on_enter(self):
        self.stage      = 'scan'
        self.networks   = []
        self.net_index  = 0
        self.password   = []
        self.char_index = 0
        self.message    = ""
        self._scan()

    def _scan(self):
        self.scanning = True
        self.message  = "Scanning..."

        def do_scan():
            try:
                result = subprocess.run(
                    ["sudo", "nmcli", "-t", "-f", "SSID,SIGNAL",
                     "dev", "wifi", "list", "--rescan", "yes"],
                    capture_output=True, text=True, timeout=15)
                seen = set()
                nets = []
                for line in result.stdout.strip().split('\n'):
                    parts = line.split(':')
                    if len(parts) >= 2 and parts[0] and parts[0] not in seen:
                        seen.add(parts[0])
                        nets.append(parts[0])
                self.networks = nets[:12]   # max 12
                self.message  = "" if nets else "No networks found"
            except Exception as e:
                self.message  = f"Scan failed: {e}"
                self.networks = []
            finally:
                self.scanning = False
                self.stage    = 'select'

        threading.Thread(target=do_scan, daemon=True).start()

    def _connect(self):
        ssid     = self.networks[self.net_index]
        password = ''.join(self.password)
        self.stage   = 'connecting'
        self.message = f"Connecting to {ssid}..."

        def do_connect():
            try:
                subprocess.run(
                    ["sudo", "nmcli", "dev", "wifi", "connect",
                     ssid, "password", password],
                    capture_output=True, text=True, timeout=30)
                # verify connection
                result = subprocess.run(
                    ["nmcli", "-t", "-f", "NAME,STATE",
                     "connection", "show", "--active"],
                    capture_output=True, text=True)
                if ssid in result.stdout:
                    self.message = f"Connected to {ssid}!"
                else:
                    self.message = "Connection failed. Check password."
            except Exception as e:
                self.message = f"Error: {e}"
            self.stage = 'done'

        threading.Thread(target=do_connect, daemon=True).start()

    def handle_input(self, action):
        if self.stage == 'scan':
            if action == 'back':
                self.app.set_screen('config')

        elif self.stage == 'select':
            if action == 'up':
                self.net_index = (self.net_index - 1) % max(1, len(self.networks))
            elif action == 'down':
                self.net_index = (self.net_index + 1) % max(1, len(self.networks))
            elif action == 'select':
                if self.networks:
                    self.stage      = 'password'
                    self.password   = []
                    self.char_index = 0
            elif action == 'back':
                self.app.set_screen('config')

        elif self.stage == 'password':
            if action == 'up':
                self.char_index = (self.char_index + 1) % len(self.CHARS)
            elif action == 'down':
                self.char_index = (self.char_index - 1) % len(self.CHARS)
            elif action == 'select':
                self.password.append(self.CHARS[self.char_index])
                self.char_index = 0
            elif action == 'back':
                if self.password:
                    self.password.pop()
                else:
                    self.stage = 'select'

        elif self.stage in ('connecting', 'done'):
            if action in ('select', 'back'):
                self.app.set_screen('config')

    def draw(self, surface):
        surface.fill(DARK_BG)
        self.draw_header(surface, "WiFi Settings")

        if self.stage == 'scan' or self.scanning:
            msg = self.app.font_large.render(
                "Scanning for networks...", True, TEXT_SECONDARY)
            surface.blit(msg, msg.get_rect(center=(SCREEN_W//2, 240)))

        elif self.stage == 'select':
            if not self.networks:
                msg = self.app.font_large.render(
                    self.message or "No networks found", True, TEXT_SECONDARY)
                surface.blit(msg, msg.get_rect(center=(SCREEN_W//2, 240)))
            else:
                y      = HEADER_H + CARD_MARGIN
                card_h = 48
                for i, ssid in enumerate(self.networks):
                    selected = (i == self.net_index)
                    bg       = CARD_HOVER if selected else CARD_BG
                    rect     = pygame.Rect(CARD_MARGIN, y,
                                           SCREEN_W - CARD_MARGIN * 2,
                                           card_h - 4)
                    draw_rounded_rect(surface, bg, rect, CARD_RADIUS)
                    if selected:
                        pygame.draw.rect(surface, ACCENT,
                                         pygame.Rect(CARD_MARGIN, y + 5,
                                                     5, card_h - 14),
                                         border_radius=3)
                    lbl = self.app.font_large.render(ssid, True, TEXT_PRIMARY)
                    surface.blit(lbl, lbl.get_rect(
                        midleft=(CARD_MARGIN + 20, y + (card_h-4)//2)))
                    y += card_h
                inst = self.app.font_small.render(
                    "SELECT to choose network  ·  BACK to cancel",
                    True, GREY)
                surface.blit(inst, inst.get_rect(
                    midbottom=(SCREEN_W//2, SCREEN_H - FOOTER_H - 6)))

        elif self.stage == 'password':
            ssid = self.networks[self.net_index]
            msg  = self.app.font_large.render(
                f"Password for:  {ssid}", True, TEXT_PRIMARY)
            surface.blit(msg, msg.get_rect(center=(SCREEN_W//2, 110)))

            # current char being selected
            cur_char = self.CHARS[self.char_index]
            char_display = self.app.font_large.render(
                f"Character:  '{cur_char}'", True, ACCENT)
            surface.blit(char_display, char_display.get_rect(
                center=(SCREEN_W//2, 180)))

            # password so far
            pw_str = ''.join(self.password) + "_"
            pw_txt = self.app.font_large.render(pw_str, True, GREEN)
            pw_bg  = pygame.Rect(CARD_MARGIN, 220,
                                 SCREEN_W - CARD_MARGIN * 2, 44)
            draw_rounded_rect(surface, CARD_BG, pw_bg, CARD_RADIUS)
            surface.blit(pw_txt, pw_txt.get_rect(
                midleft=(CARD_MARGIN + 12, 242)))

            inst1 = self.app.font_small.render(
                "▲ ▼ cycle characters", True, GREY)
            inst2 = self.app.font_small.render(
                "● add character   ✕ delete / cancel", True, GREY)
            connect_btn = pygame.Rect(CARD_MARGIN, 310,
                                      SCREEN_W - CARD_MARGIN * 2, BTN_HEIGHT)
            draw_rounded_rect(surface, ACCENT, connect_btn, CARD_RADIUS)
            conn_lbl = self.app.font_large.render(
                "Hold SELECT on space to connect →", True, WHITE)
            surface.blit(conn_lbl, conn_lbl.get_rect(
                center=connect_btn.center))
            surface.blit(inst1, inst1.get_rect(center=(SCREEN_W//2, 375)))
            surface.blit(inst2, inst2.get_rect(center=(SCREEN_W//2, 400)))

            # connect trigger: if last char added was space and
            # user presses select, connect
            if self.password and self.password[-1] == ' ':
                self.password.pop()
                self._connect()

        elif self.stage in ('connecting', 'done'):
            col = GREEN if 'Connected' in self.message else \
                  RED   if 'failed' in self.message or 'Error' in self.message \
                  else ACCENT
            msg = self.app.font_large.render(self.message, True, col)
            surface.blit(msg, msg.get_rect(center=(SCREEN_W//2, 220)))
            if self.stage == 'done':
                hint = self.app.font_small.render(
                    "Press SELECT to return", True, GREY)
                surface.blit(hint, hint.get_rect(
                    center=(SCREEN_W//2, 290)))

        self.draw_footer(surface)


# ─────────────────────────────────────────
#  Custom drink screen
# ─────────────────────────────────────────
class CustomDrinkScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.step        = 'name'
        self.name        = ""
        self.ingredients = {}
        self.pump_keys   = []
        self.index       = 0
        self.amounts     = [0,15,30,45,50,60,75,90,100,120,150,175,200]
        self.amt_indices = {}
        self.message     = ""

    def on_enter(self):
        self.step        = 'name'
        self.name        = ""
        self.ingredients = {}
        self.message     = ""
        self.pump_keys   = sorted(self.app.pump_manager.pumps.keys())
        self.amt_indices = {k: 0 for k in self.pump_keys}
        self.index       = 0

    def handle_input(self, action):
        if self.step == 'name':
            if action == 'select':
                if not self.name:
                    self.name = "My Custom Drink"
                self.step = 'ingredients'
            elif action == 'back':
                self.app.set_screen('config')
        elif self.step == 'ingredients':
            if action == 'up':
                self.index = (self.index - 1) % (len(self.pump_keys) + 1)
            elif action == 'down':
                self.index = (self.index + 1) % (len(self.pump_keys) + 1)
            elif action == 'back':
                self.step = 'name'
            elif action == 'select':
                if self.index < len(self.pump_keys):
                    key = self.pump_keys[self.index]
                    self.amt_indices[key] = \
                        (self.amt_indices[key] + 1) % len(self.amounts)
                else:
                    self._save()
        elif self.step == 'confirm':
            if action in ('select', 'back'):
                self.app.set_screen('drinks')

    def _save(self):
        ingredients = {}
        for key in self.pump_keys:
            pump = self.app.pump_manager.pumps[key]
            amt  = self.amounts[self.amt_indices[key]]
            if pump.value and amt > 0:
                ingredients[pump.value] = amt
        if not ingredients:
            self.message = "Add at least one ingredient!"
            return
        ok, msg = self.app.drink_manager.add_drink(self.name, ingredients)
        self.message = msg
        if ok:
            self.step = 'confirm'

    def _tap_ingredient(self, i):
        self.index = i
        self.handle_input('select')

    def draw(self, surface):
        surface.fill(DARK_BG)
        self.clear_hitboxes()
        self.draw_header(surface, "Create Custom Drink")

        if self.step == 'name':
            msg  = self.app.font_large.render(
                "Press SELECT to use default name,", True, TEXT_PRIMARY)
            msg2 = self.app.font_small.render(
                "or connect a keyboard to type a name.",
                True, TEXT_SECONDARY)
            name_display = self.name if self.name else "My Custom Drink"
            name_txt = self.app.font_large.render(
                f'"{name_display}"', True, ACCENT)
            surface.blit(msg,      msg.get_rect(center=(SCREEN_W//2, 200)))
            surface.blit(msg2,     msg2.get_rect(center=(SCREEN_W//2, 240)))
            surface.blit(name_txt, name_txt.get_rect(center=(SCREEN_W//2, 300)))
            self.add_hitbox(
                pygame.Rect(0, HEADER_H, SCREEN_W,
                            SCREEN_H - HEADER_H - FOOTER_H),
                lambda: self.handle_input('select'))

        elif self.step == 'ingredients':
            y      = HEADER_H + 10
            card_h = 46
            visible = 6
            scroll  = max(0, self.index - visible + 1)
            for i, key in enumerate(
                    self.pump_keys[scroll:scroll + visible]):
                actual_i = scroll + i
                pump     = self.app.pump_manager.pumps[key]
                amt      = self.amounts[self.amt_indices[key]]
                selected = (actual_i == self.index)
                bg       = CARD_HOVER if selected else CARD_BG
                rect     = pygame.Rect(CARD_MARGIN, y,
                                       SCREEN_W - CARD_MARGIN * 2, card_h - 4)
                draw_rounded_rect(surface, bg, rect, CARD_RADIUS)
                if selected:
                    pygame.draw.rect(surface, ACCENT,
                                     pygame.Rect(CARD_MARGIN, y + 5,
                                                 5, card_h - 14),
                                     border_radius=3)
                lbl = self.app.font_small.render(
                    f"{pump.name}  —  "
                    f"{pump.value if pump.value else 'Empty'}",
                    True, TEXT_PRIMARY)
                surface.blit(lbl, lbl.get_rect(
                    midleft=(CARD_MARGIN + 20, y + (card_h-4)//2)))
                amt_col = ACCENT if amt > 0 else GREY
                amt_txt = self.app.font_large.render(
                    f"{amt} ml", True, amt_col)
                surface.blit(amt_txt, amt_txt.get_rect(
                    midright=(SCREEN_W - CARD_MARGIN - 10,
                              y + (card_h-4)//2)))
                self.add_hitbox(rect, lambda i=actual_i: self._tap_ingredient(i))
                y += card_h

            save_i    = len(self.pump_keys)
            save_col  = ACCENT if self.index == save_i else ACCENT_DARK
            save_rect = pygame.Rect(CARD_MARGIN, y + 4,
                                    SCREEN_W - CARD_MARGIN * 2, 44)
            draw_rounded_rect(surface, save_col, save_rect, CARD_RADIUS)
            save_txt = self.app.font_large.render("SAVE DRINK", True, WHITE)
            surface.blit(save_txt,
                         save_txt.get_rect(center=save_rect.center))
            self.add_hitbox(save_rect, lambda i=save_i: self._tap_ingredient(i))
            if self.message:
                err = self.app.font_small.render(
                    self.message, True, AMBER)
                surface.blit(err, err.get_rect(
                    midbottom=(SCREEN_W//2, SCREEN_H - FOOTER_H - 6)))

        elif self.step == 'confirm':
            msg  = self.app.font_large.render(
                f'"{self.name}" saved!', True, GREEN)
            msg2 = self.app.font_small.render(
                "Press SELECT to return to drink menu.", True, GREY)
            surface.blit(msg,  msg.get_rect(center=(SCREEN_W//2, 220)))
            surface.blit(msg2, msg2.get_rect(center=(SCREEN_W//2, 270)))
            self.add_hitbox(
                pygame.Rect(0, HEADER_H, SCREEN_W,
                            SCREEN_H - HEADER_H - FOOTER_H),
                lambda: self.handle_input('select'))

        self.draw_nav_hint(surface)
        self.draw_footer(surface)


# ─────────────────────────────────────────
#  Main App
# ─────────────────────────────────────────
class App:
    def __init__(self, pump_manager, drink_manager, settings):
        self.pump_manager  = pump_manager
        self.drink_manager = drink_manager
        self.settings      = settings
        pygame.init()
        if not pygame.display.get_init():
            raise RuntimeError("No display available")
        pygame.mouse.set_visible(False)

        self.screen = pygame.display.set_mode(
            (SCREEN_W, SCREEN_H), pygame.NOFRAME | pygame.FULLSCREEN)
        pygame.display.set_caption("Smart Bartender")

        self.font_large = pygame.font.SysFont("dejavu sans", 24, bold=True)
        self.font_small = pygame.font.SysFont("dejavu sans", 17)

        self.selected_drink   = None
        self.pour_ingredients = {}
        self.pour_drink_name  = ""

        self.pin_screen = PinScreen(self)

        self.screens = {
            'drinks':     DrinkSelectScreen(self),
            'size':       SizeStrengthScreen(self),
            'pouring':    PouringScreen(self),
            'config':     ConfigScreen(self),
            'pumps':      PumpConfigScreen(self),
            'cleaning':   CleaningScreen(self),
            'prime':      PrimeScreen(self),
            'custom':     CustomDrinkScreen(self),
            'pin':        self.pin_screen,
            'change_pin': ChangePinScreen(self),
            'wifi':       WifiScreen(self),
        }

        self.current_screen = None
        self.set_screen('drinks')

        self._btn_state = {'up': False, 'down': False,
                           'select': False, 'back': False}
        self._key_map   = {
            pygame.K_UP:     'up',
            pygame.K_DOWN:   'down',
            pygame.K_RETURN: 'select',
            pygame.K_ESCAPE: 'back',
        }

        self.clock   = pygame.time.Clock()
        self.running = True

    def set_screen(self, name):
        self.current_screen = self.screens[name]
        self.current_screen.on_enter()

    def _read_buttons(self):
        actions = []
        if SIMULATION or not GPIO_BUTTONS:
            return actions
        for action, btn in GPIO_BUTTONS.items():
            pressed = btn.is_pressed
            if pressed and not self._btn_state.get(action, False):
                actions.append(action)
            self._btn_state[action] = pressed
        return actions

    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    action = self._key_map.get(event.key)
                    if action:
                        self.current_screen.handle_input(action)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    # Touchscreen taps arrive as mouse events (evdev/
                    # libinput reports the Waveshare panel as a pointer
                    # device). event.pos is already in screen pixels.
                    self.current_screen.handle_touch(event.pos)
                elif event.type == pygame.USEREVENT + 1:
                    pygame.time.set_timer(pygame.USEREVENT + 1, 0)
                    self.set_screen('drinks')

            for action in self._read_buttons():
                self.current_screen.handle_input(action)

            self.current_screen.draw(self.screen)
            pygame.display.flip()
            self.clock.tick(30)

        pygame.quit()
        self.pump_manager.cleanup()
        sys.exit()
