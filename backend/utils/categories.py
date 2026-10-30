"""Document categories, stored in data/categories.json as {"file name": "category"}."""

from utils.config import CATEGORIES_FILE
from utils.storage import load_json, lock, save_json

DEFAULT_CATEGORY = "General"


def load_categories():
    return load_json(CATEGORIES_FILE, {})


def get_category(name, categories):
    return categories.get(name, DEFAULT_CATEGORY)


def set_category(name, category):
    """Save a document's category (max 30 characters, "General" if empty) and return it."""
    category = category.strip()[:30] or DEFAULT_CATEGORY
    with lock:
        categories = load_categories()
        categories[name] = category
        save_json(CATEGORIES_FILE, categories, indent=2)
    return category


def remove_category(name):
    with lock:
        categories = load_categories()
        if categories.pop(name, None):
            save_json(CATEGORIES_FILE, categories, indent=2)
