import json
import os

DRINKS_PATH = "config/drinks.json"

# Default drink menu - all amounts in ml
DEFAULT_DRINKS = [
    {
        "name": "Rum & Coke",
        "ingredients": {"rum": 50, "coke": 150}
    },
    {
        "name": "Gin & Tonic",
        "ingredients": {"gin": 50, "tonic": 150}
    },
    {
        "name": "Screwdriver",
        "ingredients": {"vodka": 50, "oj": 150}
    },
    {
        "name": "Margarita",
        "ingredients": {"tequila": 50, "margarita_mix": 150}
    },
    {
        "name": "Tequila Sunrise",
        "ingredients": {"tequila": 50, "oj": 150}
    },
    {
        "name": "Gin & Juice",
        "ingredients": {"gin": 50, "oj": 150}
    },
    {
        "name": "Long Island",
        "ingredients": {
            "gin": 15,
            "rum": 15,
            "vodka": 15,
            "tequila": 15,
            "coke": 100,
            "oj": 30
        }
    },
    {
        "name": "Vodka Soda",
        "ingredients": {"vodka": 50, "soda": 150}
    },
    {
        "name": "Rum & Juice",
        "ingredients": {"rum": 50, "oj": 150}
    },
    {
        "name": "Paloma",
        "ingredients": {"tequila": 50, "grapefruit": 150}
    },
]

# Every possible liquid that can be loaded into a pump.
# Add more here any time you want a new option to appear
# in the pump configuration menu.
DRINK_OPTIONS = [
    {"name": "Gin",            "value": "gin"},
    {"name": "Rum",            "value": "rum"},
    {"name": "Vodka",          "value": "vodka"},
    {"name": "Tequila",        "value": "tequila"},
    {"name": "Tonic Water",    "value": "tonic"},
    {"name": "Soda Water",     "value": "soda"},
    {"name": "Coke",           "value": "coke"},
    {"name": "Orange Juice",   "value": "oj"},
    {"name": "Grapefruit Juice","value": "grapefruit"},
    {"name": "Margarita Mix",  "value": "margarita_mix"},
    {"name": "Cranberry Juice","value": "cranberry"},
    {"name": "Pineapple Juice","value": "pineapple"},
    {"name": "Lemonade",       "value": "lemonade"},
    {"name": "Grenadine",      "value": "grenadine"},
    {"name": "Water",          "value": "water"},
]

# Size multipliers - applied to every ingredient amount
SIZES = {
    "Small":  0.75,
    "Regular": 1.0,
    "Large":  1.5,
}

# Strength multipliers - applied to alcohol ingredients only.
# We need to know which ingredients are alcoholic so we can
# scale just those, leaving mixers unchanged.
ALCOHOLS = {
    "gin", "rum", "vodka", "tequila", "whiskey",
    "bourbon", "brandy", "triple_sec", "kahlua"
}

STRENGTHS = {
    "Normal": 1.0,
    "Double": 2.0,
}


class DrinkManager:
    def __init__(self):
        self.drinks = []
        self.load()

    def load(self):
        """Loads drinks from file, or creates defaults if file doesn't exist."""
        if os.path.exists(DRINKS_PATH):
            with open(DRINKS_PATH, "r") as f:
                self.drinks = json.load(f)
        else:
            self.drinks = list(DEFAULT_DRINKS)
            self.save()
        print(f"Loaded {len(self.drinks)} drinks")

    def save(self):
        os.makedirs("config", exist_ok=True)
        with open(DRINKS_PATH, "w") as f:
            json.dump(self.drinks, f, indent=2)

    def get_available_drinks(self, available_ingredients):
        """
        Returns only drinks that can be made with what's
        currently loaded in the pumps.
        available_ingredients is a set of ingredient values.
        """
        available = []
        for drink in self.drinks:
            needed = set(drink["ingredients"].keys())
            if needed.issubset(available_ingredients):
                available.append(drink)
        return available

    def scale_ingredients(self, ingredients, size="Regular", strength="Normal"):
        """
        Returns a new ingredient dict with amounts adjusted
        for the chosen size and strength.
        """
        size_mult = SIZES.get(size, 1.0)
        strength_mult = STRENGTHS.get(strength, 1.0)
        scaled = {}
        for ingredient, amount in ingredients.items():
            amount = amount * size_mult
            if ingredient in ALCOHOLS:
                amount = amount * strength_mult
            scaled[ingredient] = round(amount, 1)
        return scaled

    def add_drink(self, name, ingredients):
        """Adds a new custom drink and saves it."""
        # Check for duplicate names
        for drink in self.drinks:
            if drink["name"].lower() == name.lower():
                return False, "A drink with that name already exists."
        self.drinks.append({"name": name, "ingredients": ingredients})
        self.save()
        return True, "Drink saved!"

    def delete_drink(self, name):
        """Deletes a drink by name."""
        before = len(self.drinks)
        self.drinks = [d for d in self.drinks if d["name"] != name]
        if len(self.drinks) < before:
            self.save()
            return True
        return False

    def get_drink_by_name(self, name):
        for drink in self.drinks:
            if drink["name"] == name:
                return drink
        return None
