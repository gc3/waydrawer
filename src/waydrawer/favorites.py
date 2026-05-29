# ----------- Favorites -------------------------------------------------------
"""
  A simple module for tracking which apps have been 'favorited' by the user.
"""
from __future__ import annotations

import json
from waydrawer.config import CONFIG_DIR

FAVORITES_FILE = CONFIG_DIR / "favorites.json"

def load_favorites() -> list[str]:
  """ Load favorites from the config directory """
  try:
    return json.loads(FAVORITES_FILE.read_text())

  except (FileNotFoundError, json.JSONDecodeError):
    return []

def save_favorites(ids: list[str]) -> None:
  """ Write out favorites to the config directory """
  CONFIG_DIR.mkdir(parents=True, exist_ok=True)
  FAVORITES_FILE.write_text(json.dumps(ids, indent=2))
