import pygame
import sys
import threading
import time
import os

# ─────────────────────────────────────────
#  Display settings
# ─────────────────────────────────────────
SCREEN_W = 800
SCREEN_H = 480

# ─────────────────────────────────────────
#  Colours  (R, G, B)
# ─────────────────────────────────────────
BLACK       = (  0,   0,   0)
WHITE       = (255, 255, 255)
DARK_BG     = ( 18,  18,  18)
CARD_BG     = ( 30,  30,  30)
CARD_HOVER  = ( 45,  45,  45)
ACCENT      = ( 52, 152, 219)   # blue
ACCENT_DARK = ( 31,  97, 141)
GREEN       = ( 46, 204, 113)
RED         = (231,  76,  60)
AMBER       = (243, 156,  18)
GREY        = (127, 140, 141)
TEXT_PRIMARY   = (236, 240, 241)
TEXT_SECONDARY = (149, 165, 166)

# ─────────────────────────────────────────
#  Layout constants
# ─────────────────────────────────────────
CARD_MARGIN  = 16
CARD_RADIUS  = 12
BTN_HEIGHT   = 56
HEADER_H     = 64

# ─────────────────────────────────────────
#  Button GPIO pins
# ─────────────────────────────────────────
BTN_UP     = 5
BTN_DOWN   = 6
BTN_SELECT = 13
BTN_BACK   = 19

SIMULATION = True   # set False when real buttons are wired up

try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    for pin in [BTN_UP, BTN_DOWN, BTN_SELECT, BTN_BACK]:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
except (ImportError, RuntimeError):
    GPIO = None
    SIMULATION = True


def draw_rounded_rect(surface, colour, rect, radius):
    pygame.draw.rect(surface, colour, rect, border_radius=radius)


class Button:
    """A single on-screen card/button."""
    def __init__(self, rect, label, sublabel=None, colour=CARD_BG,
                 text_colour=TEXT_PRIMARY, accent_bar=None):
        self.rect       = pygame.Rect(rect)
        self.label      = label
        self.sublabel   = sublabel
        self.colour     = colour
        self.text_colour= text_colour
        self.accent_bar = accent_bar   # colour of left accent stripe, or None
        self.selected   = False

    def draw(self, surface, font_large, font_small):
        colour = CARD_HOVER if self.selected else self.colour
        draw_rounded_rect(surface, colour, self.rect, CARD_RADIUS)

        # left accent bar when selected
        if self.selected:
            bar = pygame.Rect(self.rect.x, self.rect.y + 8,
                              5, self.rect.height - 16)
            pygame.draw.rect(surface, ACCENT, bar, border_radius=3)

        # label
        cx = self.rect.centerx
        if self.sublabel:
            cy = self.rect.centery - 10
        else:
            cy = self.rect.centery

        txt = font_large.render(self.label, True, self.text_colour)
        surface.blit(txt, txt.get_rect(center=(cx, cy)))

        if self.sublabel:
            sub = font_small.render(self.sublabel, True, TEXT_SECONDARY)
            surface.blit(sub, sub.get_rect(center=(cx, self.rect.centery + 14)))


class Screen:
    """Base class for every screen in the app."""
    def __init__(self, app):
        self.app = app

    def on_enter(self):
        """Called when this screen becomes active."""
        pass

    def handle_input(self, action):
        """
        action is one of: 'up', 'down', 'select', 'back'
        Override in subclasses.
        """
        pass

    def draw(self, surface):
        """Override to draw the screen."""
        pass

    def draw_header(self, surface, title, show_back=True):
        """Draws the top bar shared by all screens."""
        pygame.draw.rect(surface, CARD_BG,
                         pygame.Rect(0, 0, SCREEN_W, HEADER_H))
        font = self.app.font_large
        txt = font.render(title, True, TEXT_PRIMARY)
        surface.blit(txt, txt.get_rect(midleft=(20, HEADER_H // 2)))

        if show_back:
            hint = self.app.font_small.render("[ BACK ]", True, TEXT_SECONDARY)
            surface.blit(hint, hint.get_rect(midright=(SCREEN_W - 20,
                                                        HEADER_H // 2)))

    def draw_nav_hint(self, surface):
        """Draws ▲ ▼ navigation hint at the bottom."""
        hint = self.app.font_small.render(
            "▲ ▼  scroll       ● select       ✕ back",
            True, GREY)
        surface.blit(hint, hint.get_rect(
            midbottom=(SCREEN_W // 2, SCREEN_H - 6)))


class DrinkSelectScreen(Screen):
    """Main screen — shows available drinks as scrollable cards."""
    def __init__(self, app):
        super().__init__(app)
        self.drinks     = []
        self.index      = 0
        self.scroll_off = 0
        self.cards_visible = 4

    def on_enter(self):
        available_ing = self.app.pump_manager.get_available_ingredients()
        self.drinks   = self.app.drink_manager.get_available_drinks(available_ing)
        self.index    = 0
        self.scroll_off = 0

        if not self.drinks:
            # No drinks available - go straight to config hint
            pass

    def handle_input(self, action):
        if not self.drinks:
            if action == 'select':
                self.app.set_screen('config')
            return

        if action == 'up':
            self.index = (self.index - 1) % len(self.drinks)
        elif action == 'down':
            self.index = (self.index + 1) % len(self.drinks)
        elif action == 'select':
            drink = self.drinks[self.index]
            self.app.selected_drink = drink
            self.app.set_screen('size')
        elif action == 'back':
            self.app.set_screen('config')

        # keep selected card visible
        if self.index < self.scroll_off:
            self.scroll_off = self.index
        elif self.index >= self.scroll_off + self.cards_visible:
            self.scroll_off = self.index - self.cards_visible + 1

    def draw(self, surface):
        surface.fill(DARK_BG)
        self.draw_header(surface, "🍹  Smart Bartender", show_back=False)

        if not self.drinks:
            msg  = self.app.font_large.render(
                "No drinks available", True, TEXT_SECONDARY)
            msg2 = self.app.font_small.render(
                "Configure pumps first  →  press SELECT", True, GREY)
            surface.blit(msg,  msg.get_rect(center=(SCREEN_W//2, 220)))
            surface.blit(msg2, msg2.get_rect(center=(SCREEN_W//2, 265)))
            return

        y = HEADER_H + CARD_MARGIN
        card_h = (SCREEN_H - HEADER_H - 40 - CARD_MARGIN) // self.cards_visible

        visible = self.drinks[self.scroll_off:
                               self.scroll_off + self.cards_visible]
        for i, drink in enumerate(visible):
            actual_i = self.scroll_off + i
            ing_names = ", ".join(drink["ingredients"].keys())
            btn = Button(
                rect=(CARD_MARGIN, y, SCREEN_W - CARD_MARGIN * 2, card_h - 6),
                label=drink["name"],
                sublabel=ing_names,
                colour=CARD_BG
            )
            btn.selected = (actual_i == self.index)
            btn.draw(surface, self.app.font_large, self.app.font_small)
            y += card_h

        # scroll indicator
        if len(self.drinks) > self.cards_visible:
            total = len(self.drinks)
            bar_h = SCREEN_H - HEADER_H - 40
            thumb_h = max(30, bar_h * self.cards_visible // total)
            thumb_y = HEADER_H + (bar_h - thumb_h) * self.scroll_off // max(1, total - self.cards_visible)
            pygame.draw.rect(surface, GREY,
                             (SCREEN_W - 6, HEADER_H, 4, bar_h), border_radius=2)
            pygame.draw.rect(surface, ACCENT,
                             (SCREEN_W - 6, thumb_y, 4, thumb_h), border_radius=2)

        self.draw_nav_hint(surface)


class SizeStrengthScreen(Screen):
    """Lets the user pick size and strength before pouring."""
    SIZES     = ["Small", "Regular", "Large"]
    STRENGTHS = ["Normal", "Double"]

    def __init__(self, app):
        super().__init__(app)
        self.size_idx     = 1   # default Regular
        self.strength_idx = 0   # default Normal
        self.row          = 0   # 0 = size row, 1 = strength row, 2 = pour button

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
                self.strength_idx = (self.strength_idx + 1) % len(self.STRENGTHS)
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

    def draw(self, surface):
        surface.fill(DARK_BG)
        drink = self.app.selected_drink
        self.draw_header(surface, drink["name"] if drink else "")

        labels = [
            ("Size",     self.SIZES[self.size_idx]),
            ("Strength", self.STRENGTHS[self.strength_idx]),
        ]

        y = HEADER_H + 30
        for i, (label, value) in enumerate(labels):
            selected = (self.row == i)
            bg = CARD_HOVER if selected else CARD_BG
            rect = pygame.Rect(CARD_MARGIN, y,
                               SCREEN_W - CARD_MARGIN * 2, BTN_HEIGHT)
            draw_rounded_rect(surface, bg, rect, CARD_RADIUS)
            if selected:
                pygame.draw.rect(surface, ACCENT,
                                 pygame.Rect(CARD_MARGIN, y + 8, 5,
                                             BTN_HEIGHT - 16),
                                 border_radius=3)

            lbl = self.app.font_small.render(label, True, TEXT_SECONDARY)
            val = self.app.font_large.render(value, True, TEXT_PRIMARY)
            surface.blit(lbl, lbl.get_rect(midleft=(CARD_MARGIN + 20,
                                                     y + BTN_HEIGHT // 2 - 10)))
            surface.blit(val, val.get_rect(midleft=(CARD_MARGIN + 20,
                                                     y + BTN_HEIGHT // 2 + 12)))
            hint = self.app.font_small.render("← press SELECT to change →",
                                              True, ACCENT if selected else GREY)
            surface.blit(hint, hint.get_rect(midright=(SCREEN_W - CARD_MARGIN - 10,
                                                        y + BTN_HEIGHT // 2)))
            y += BTN_HEIGHT + 10

        # Pour button
        y += 10
        pour_rect = pygame.Rect(CARD_MARGIN, y,
                                SCREEN_W - CARD_MARGIN * 2, BTN_HEIGHT + 10)
        colour = ACCENT if self.row == 2 else ACCENT_DARK
        draw_rounded_rect(surface, colour, pour_rect, CARD_RADIUS)
        pour_lbl = self.app.font_large.render("POUR DRINK", True, WHITE)
        surface.blit(pour_lbl, pour_lbl.get_rect(center=pour_rect.center))

        self.draw_nav_hint(surface)


class PouringScreen(Screen):
    """Shows a progress bar while the drink is being poured."""
    def __init__(self, app):
        super().__init__(app)
        self.progress  = 0
        self.done      = False
        self.warnings  = []

    def on_enter(self):
        self.progress = 0
        self.done     = False
        self.warnings = []

        def on_progress(pct):
            self.progress = pct

        def on_complete():
            self.done = True
            # check for low pumps after pouring
            low = self.app.pump_manager.get_low_pumps()
            self.warnings = [f"{p.name} ({p.value}) is low!" for p in low]
            pygame.time.set_timer(pygame.USEREVENT + 1, 3000)  # auto-advance

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
        name = self.app.pour_drink_name or "Drink"
        self.draw_header(surface, f"Pouring  {name}...", show_back=False)

        # progress bar background
        bar_x = CARD_MARGIN * 3
        bar_y = 200
        bar_w = SCREEN_W - CARD_MARGIN * 6
        bar_h = 32
        pygame.draw.rect(surface, CARD_BG,
                         (bar_x, bar_y, bar_w, bar_h), border_radius=8)

        # progress bar fill
        fill_w = int(bar_w * self.progress / 100)
        if fill_w > 0:
            colour = GREEN if self.done else ACCENT
            pygame.draw.rect(surface, colour,
                             (bar_x, bar_y, fill_w, bar_h), border_radius=8)

        # percentage text
        pct_txt = self.app.font_large.render(
            f"{self.progress}%", True, TEXT_PRIMARY)
        surface.blit(pct_txt, pct_txt.get_rect(center=(SCREEN_W // 2, 270)))

        if self.done:
            done_txt = self.app.font_large.render(
                "Enjoy your drink! 🎉", True, GREEN)
            surface.blit(done_txt,
                         done_txt.get_rect(center=(SCREEN_W // 2, 330)))

            for i, w in enumerate(self.warnings):
                warn = self.app.font_small.render(f"⚠  {w}", True, AMBER)
                surface.blit(warn, warn.get_rect(
                    center=(SCREEN_W // 2, 380 + i * 24)))

            hint = self.app.font_small.render(
                "Press SELECT to return to menu", True, GREY)
            surface.blit(hint, hint.get_rect(
                midbottom=(SCREEN_W // 2, SCREEN_H - 10)))


class ConfigScreen(Screen):
    """Configuration menu — pumps, clean, custom drinks."""
    OPTIONS = ["Configure Pumps", "Clean All Pumps", "Add Custom Drink", "Back to Drinks"]

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
            elif choice == "Add Custom Drink":
                self.app.set_screen('custom')
            elif choice == "Back to Drinks":
                self.app.set_screen('drinks')

    def draw(self, surface):
        surface.fill(DARK_BG)
        self.draw_header(surface, "Configuration")

        y = HEADER_H + CARD_MARGIN
        card_h = 72

        for i, opt in enumerate(self.OPTIONS):
            selected = (i == self.index)
            bg = CARD_HOVER if selected else CARD_BG
            rect = pygame.Rect(CARD_MARGIN, y,
                               SCREEN_W - CARD_MARGIN * 2, card_h - 6)
            draw_rounded_rect(surface, bg, rect, CARD_RADIUS)
            if selected:
                pygame.draw.rect(surface, ACCENT,
                                 pygame.Rect(CARD_MARGIN, y + 8, 5,
                                             card_h - 22), border_radius=3)
            lbl = self.app.font_large.render(opt, True, TEXT_PRIMARY)
            surface.blit(lbl, lbl.get_rect(midleft=(CARD_MARGIN + 20,
                                                     y + (card_h - 6) // 2)))
            y += card_h

        self.draw_nav_hint(surface)


class PumpConfigScreen(Screen):
    """Lets the user assign a liquid and volume to each pump."""
    def __init__(self, app):
        super().__init__(app)
        self.pump_keys = []
        self.index     = 0
        self.editing   = None   # which pump is being edited
        self.edit_row  = 0      # 0 = liquid, 1 = volume, 2 = done

        # Volume options in ml (common bottle sizes)
        self.volumes = [0, 50, 100, 200, 375, 500, 750, 1000, 1750]
        self.vol_idx = 0

        # Ingredient options from drinks.py
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

        # set selectors to current pump values
        current_val = pump.value
        self.opt_idx = 0
        for i, opt in enumerate(self.options):
            if opt["value"] == current_val:
                self.opt_idx = i
                break

        current_vol = pump.volume_ml
        self.vol_idx = 0
        for i, v in enumerate(self.volumes):
            if v == current_vol:
                self.vol_idx = i
                break

    def _save_edit(self):
        pump = self.app.pump_manager.pumps[self.editing]
        pump.value     = self.options[self.opt_idx]["value"]
        pump.volume_ml = self.volumes[self.vol_idx]
        self.app.pump_manager.save()
        self.editing = None

    def handle_input(self, action):
        if self.editing is None:
            # browsing pump list
            if action == 'up':
                self.index = (self.index - 1) % len(self.pump_keys)
            elif action == 'down':
                self.index = (self.index + 1) % len(self.pump_keys)
            elif action == 'select':
                self._start_editing()
            elif action == 'back':
                self.app.set_screen('config')
        else:
            # editing a pump
            if action == 'back':
                self.editing = None
                return
            if action == 'up':
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

    def draw(self, surface):
        surface.fill(DARK_BG)
        self.draw_header(surface, "Configure Pumps")

        if self.editing:
            self._draw_edit(surface)
        else:
            self._draw_list(surface)

        self.draw_nav_hint(surface)

    def _draw_list(self, surface):
        y = HEADER_H + CARD_MARGIN
        card_h = 54
        visible_count = 5
        scroll = max(0, self.index - visible_count + 1)
        keys_to_show = self.pump_keys[scroll:scroll + visible_count]

        for i, key in enumerate(keys_to_show):
            actual_i = scroll + i
            pump     = self.app.pump_manager.pumps[key]
            selected = (actual_i == self.index)
            bg = CARD_HOVER if selected else CARD_BG

            rect = pygame.Rect(CARD_MARGIN, y,
                               SCREEN_W - CARD_MARGIN * 2, card_h - 4)
            draw_rounded_rect(surface, bg, rect, CARD_RADIUS)

            if selected:
                pygame.draw.rect(surface, ACCENT,
                                 pygame.Rect(CARD_MARGIN, y + 6,
                                             5, card_h - 16),
                                 border_radius=3)

            # pump name
            name_txt = self.app.font_large.render(
                pump.name, True, TEXT_PRIMARY)
            surface.blit(name_txt, name_txt.get_rect(
                midleft=(CARD_MARGIN + 20, y + (card_h - 4) // 2 - 8)))

            # liquid and volume
            liquid = pump.value if pump.value else "Empty"
            vol    = f"{pump.volume_ml}ml"
            sub    = self.app.font_small.render(
                f"{liquid}  ·  {vol}", True,
                AMBER if pump.is_low() else TEXT_SECONDARY)
            surface.blit(sub, sub.get_rect(
                midleft=(CARD_MARGIN + 20, y + (card_h - 4) // 2 + 10)))

            # low warning badge
            if pump.is_low():
                warn = self.app.font_small.render("LOW", True, AMBER)
                surface.blit(warn, warn.get_rect(
                    midright=(SCREEN_W - CARD_MARGIN - 10,
                              y + (card_h - 4) // 2)))

            y += card_h

    def _draw_edit(self, surface):
        pump = self.app.pump_manager.pumps[self.editing]
        title = self.app.font_large.render(
            f"Editing  {pump.name}", True, ACCENT)
        surface.blit(title, title.get_rect(
            midleft=(CARD_MARGIN, HEADER_H + 20)))

        rows = [
            ("Liquid",  self.options[self.opt_idx]["name"]),
            ("Volume",  f"{self.volumes[self.vol_idx]} ml"),
            ("",        "SAVE"),
        ]

        y = HEADER_H + 60
        for i, (label, value) in enumerate(rows):
            selected = (i == self.edit_row)
            bg = CARD_HOVER if selected else CARD_BG
            rect = pygame.Rect(CARD_MARGIN, y,
                               SCREEN_W - CARD_MARGIN * 2, BTN_HEIGHT)
            draw_rounded_rect(surface, ACCENT if (selected and i == 2)
                              else bg, rect, CARD_RADIUS)

            if selected and i < 2:
                pygame.draw.rect(surface, ACCENT,
                                 pygame.Rect(CARD_MARGIN, y + 8,
                                             5, BTN_HEIGHT - 16),
                                 border_radius=3)

            if label:
                lbl = self.app.font_small.render(label, True, TEXT_SECONDARY)
                surface.blit(lbl, lbl.get_rect(
                    midleft=(CARD_MARGIN + 20, y + BTN_HEIGHT // 2 - 10)))

            val_colour = WHITE if (selected and i == 2) else TEXT_PRIMARY
            val = self.app.font_large.render(value, True, val_colour)
            surface.blit(val, val.get_rect(
                midleft=(CARD_MARGIN + 20, y + BTN_HEIGHT // 2 + 10)
                if label else rect.center))

            if selected and i < 2:
                hint = self.app.font_small.render(
                    "← SELECT to cycle →", True, ACCENT)
                surface.blit(hint, hint.get_rect(
                    midright=(SCREEN_W - CARD_MARGIN - 10,
                              y + BTN_HEIGHT // 2)))
            y += BTN_HEIGHT + 10


class CleaningScreen(Screen):
    """Runs all pumps simultaneously to flush the tubes."""
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
            on_complete=on_complete
        )

    def draw(self, surface):
        surface.fill(DARK_BG)
        self.draw_header(surface, "Clean All Pumps")

        if not self.started:
            msg = self.app.font_large.render(
                "Hook tubes up to water first.", True, TEXT_PRIMARY)
            msg2 = self.app.font_small.render(
                "All pumps will run for 20 seconds.", True, TEXT_SECONDARY)
            msg3 = self.app.font_small.render(
                "Press SELECT to start  ·  BACK to cancel",
                True, GREY)
            surface.blit(msg,  msg.get_rect(center=(SCREEN_W // 2, 200)))
            surface.blit(msg2, msg2.get_rect(center=(SCREEN_W // 2, 245)))
            surface.blit(msg3, msg3.get_rect(center=(SCREEN_W // 2, 290)))
            return

        bar_x = CARD_MARGIN * 3
        bar_y = 200
        bar_w = SCREEN_W - CARD_MARGIN * 6
        bar_h = 32
        pygame.draw.rect(surface, CARD_BG,
                         (bar_x, bar_y, bar_w, bar_h), border_radius=8)
        fill_w = int(bar_w * self.progress / 100)
        if fill_w > 0:
            colour = GREEN if self.done else ACCENT
            pygame.draw.rect(surface, colour,
                             (bar_x, bar_y, fill_w, bar_h), border_radius=8)

        pct = self.app.font_large.render(
            f"{self.progress}%", True, TEXT_PRIMARY)
        surface.blit(pct, pct.get_rect(center=(SCREEN_W // 2, 260)))

        if self.done:
            done = self.app.font_large.render(
                "Cleaning complete!", True, GREEN)
            surface.blit(done, done.get_rect(center=(SCREEN_W // 2, 320)))
            hint = self.app.font_small.render(
                "Press SELECT to return", True, GREY)
            surface.blit(hint, hint.get_rect(
                midbottom=(SCREEN_W // 2, SCREEN_H - 10)))


class CustomDrinkScreen(Screen):
    """Allows the user to create a new drink using loaded pumps."""
    def __init__(self, app):
        super().__init__(app)
        self.step       = 'name'   # name → ingredients → confirm
        self.name       = ""
        self.ingredients= {}
        self.pump_keys  = []
        self.index      = 0
        self.amounts    = [0, 15, 30, 45, 50, 60, 75, 90, 100, 120, 150, 175, 200]
        self.amt_indices= {}
        self.message    = ""

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
            # Name entry is keyboard only for now
            # Physical button shortcut: SELECT skips to a default name
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
                    self.amt_indices[key] = (
                        (self.amt_indices[key] + 1) % len(self.amounts))
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

    def draw(self, surface):
        surface.fill(DARK_BG)
        self.draw_header(surface, "Create Custom Drink")

        if self.step == 'name':
            msg = self.app.font_large.render(
                "Press SELECT to use default name,", True, TEXT_PRIMARY)
            msg2 = self.app.font_small.render(
                "or connect a keyboard to type a custom name.",
                True, TEXT_SECONDARY)
            name_display = self.name if self.name else "My Custom Drink"
            name_txt = self.app.font_large.render(
                f'"{name_display}"', True, ACCENT)
            surface.blit(msg,       msg.get_rect(center=(SCREEN_W//2, 200)))
            surface.blit(msg2,      msg2.get_rect(center=(SCREEN_W//2, 240)))
            surface.blit(name_txt,  name_txt.get_rect(center=(SCREEN_W//2, 300)))

        elif self.step == 'ingredients':
            y = HEADER_H + 10
            card_h = 46
            visible = 6
            scroll  = max(0, self.index - visible + 1)

            keys_show = self.pump_keys[scroll:scroll + visible]
            for i, key in enumerate(keys_show):
                actual_i = scroll + i
                pump     = self.app.pump_manager.pumps[key]
                amt      = self.amounts[self.amt_indices[key]]
                selected = (actual_i == self.index)
                bg = CARD_HOVER if selected else CARD_BG

                rect = pygame.Rect(CARD_MARGIN, y,
                                   SCREEN_W - CARD_MARGIN * 2, card_h - 4)
                draw_rounded_rect(surface, bg, rect, CARD_RADIUS)

                if selected:
                    pygame.draw.rect(surface, ACCENT,
                                     pygame.Rect(CARD_MARGIN, y + 5,
                                                 5, card_h - 14),
                                     border_radius=3)

                liquid = pump.value if pump.value else "Empty"
                lbl = self.app.font_small.render(
                    f"{pump.name}  —  {liquid}", True, TEXT_PRIMARY)
                surface.blit(lbl, lbl.get_rect(
                    midleft=(CARD_MARGIN + 20, y + (card_h - 4) // 2)))

                amt_colour = ACCENT if amt > 0 else GREY
                amt_txt = self.app.font_large.render(
                    f"{amt} ml", True, amt_colour)
                surface.blit(amt_txt, amt_txt.get_rect(
                    midright=(SCREEN_W - CARD_MARGIN - 10,
                              y + (card_h - 4) // 2)))
                y += card_h

            # Save button
            if self.index == len(self.pump_keys):
                save_col = ACCENT
            else:
                save_col = ACCENT_DARK
            save_rect = pygame.Rect(CARD_MARGIN, y + 4,
                                    SCREEN_W - CARD_MARGIN * 2, 44)
            draw_rounded_rect(surface, save_col, save_rect, CARD_RADIUS)
            save_txt = self.app.font_large.render("SAVE DRINK", True, WHITE)
            surface.blit(save_txt, save_txt.get_rect(center=save_rect.center))

            if self.message:
                err = self.app.font_small.render(self.message, True, AMBER)
                surface.blit(err, err.get_rect(
                    midbottom=(SCREEN_W // 2, SCREEN_H - 10)))

        elif self.step == 'confirm':
            msg = self.app.font_large.render(
                f'"{self.name}" saved!', True, GREEN)
            msg2 = self.app.font_small.render(
                "Press SELECT to return to drink menu.", True, GREY)
            surface.blit(msg,  msg.get_rect(center=(SCREEN_W // 2, 220)))
            surface.blit(msg2, msg2.get_rect(center=(SCREEN_W // 2, 270)))

        self.draw_nav_hint(surface)

class App:
    """Main application — owns the pygame loop and all screens."""
    def __init__(self, pump_manager, drink_manager):
        self.pump_manager  = pump_manager
        self.drink_manager = drink_manager

        os.environ.setdefault("SDL_VIDEODRIVER", "wayland")

        pygame.init()
        pygame.mouse.set_visible(False)
        self.screen = pygame.display.set_mode(
            (SCREEN_W, SCREEN_H), pygame.NOFRAME)
        pygame.display.set_caption("Smart Bartender")

        self.font_large = pygame.font.SysFont("dejavu sans", 24, bold=True)
        self.font_small = pygame.font.SysFont("dejavu sans", 17)

        # Shared state between screens
        self.selected_drink    = None
        self.pour_ingredients  = {}
        self.pour_drink_name   = ""

        # Register all screens
        self.screens = {
            'drinks':  DrinkSelectScreen(self),
            'size':    SizeStrengthScreen(self),
            'pouring': PouringScreen(self),
            'config':  ConfigScreen(self),
            'pumps':   PumpConfigScreen(self),
            'cleaning': CleaningScreen(self),
            'custom':  CustomDrinkScreen(self),
        }
        self.current_screen = None
        self.set_screen('drinks')

        # Button state for debouncing
        self._btn_state  = {BTN_UP: False, BTN_DOWN: False,
                            BTN_SELECT: False, BTN_BACK: False}
        self._btn_map    = {BTN_UP: 'up', BTN_DOWN: 'down',
                            BTN_SELECT: 'select', BTN_BACK: 'back'}

        # Keyboard fallback for testing (arrow keys + enter + escape)
        self._key_map = {
            pygame.K_UP:     'up',
            pygame.K_DOWN:   'down',
            pygame.K_RETURN: 'select',
            pygame.K_ESCAPE: 'back',
        }

        self.clock = pygame.time.Clock()
        self.running = True

    def set_screen(self, name):
        self.current_screen = self.screens[name]
        self.current_screen.on_enter()

    def _read_buttons(self):
        """Polls GPIO buttons and returns any new presses."""
        actions = []
        if SIMULATION or not GPIO:
            return actions
        for pin, action in self._btn_map.items():
            pressed = GPIO.input(pin) == GPIO.LOW
            if pressed and not self._btn_state[pin]:
                actions.append(action)
            self._btn_state[pin] = pressed
        return actions

    def run(self):
        while self.running:
            # ── Events ──────────────────────────────────
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                elif event.type == pygame.KEYDOWN:
                    action = self._key_map.get(event.key)
                    if action:
                        self.current_screen.handle_input(action)

                elif event.type == pygame.USEREVENT + 1:
                    # Auto-advance after pouring is done
                    pygame.time.set_timer(pygame.USEREVENT + 1, 0)
                    self.set_screen('drinks')

            # ── GPIO buttons ────────────────────────────
            for action in self._read_buttons():
                self.current_screen.handle_input(action)

            # ── Draw ────────────────────────────────────
            self.current_screen.draw(self.screen)
            pygame.display.flip()
            self.clock.tick(30)

        pygame.quit()
        if not SIMULATION and GPIO:
            GPIO.cleanup()
        sys.exit()
