# ----------- Config ----------------------------------------------------------
"""
  Read the user's config file in ~/.config/waydrawer/config.toml or give them
  the default values listed below if there's no file. This will ignore unknown
  keys in the config file but give a warning for unknown keys.
"""
from __future__ import annotations

import sys
import tomllib  # py 3.11+

from pathlib import Path
from gi.repository import GLib

APP_NAME = "waydrawer"
CONFIG_DIR = Path(GLib.get_user_config_dir()) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.toml"
FAVORITES_FILE = CONFIG_DIR / "favorites.json"

# defaults for config file entries if we have no file
CFG_DEFAULTS = {
  "columns": 6,
  "icon_size": 64,
  "search_url": "https://duckduckgo.com/?q={}",
}

# .desktop Categories= -> display bucket. First match wins.
CATEGORY_MAP = {
  "AudioVideo": "Media", "Audio": "Media", "Video": "Media",
  "Player": "Media", "Music": "Media",
  "Development": "Development", "IDE": "Development",
  "Education": "Education",
  "Game": "Games",
  "Graphics": "Graphics", "Photography": "Graphics",
  "Network": "Internet", "WebBrowser": "Internet",
  "Email": "Internet", "Chat": "Internet", "InstantMessaging": "Internet",
  "Office": "Office", "WordProcessor": "Office", "Spreadsheet": "Office",
  "Science": "Science",
  "Settings": "System", "System": "System",
  "Utility": "Utilities", "Accessories": "Utilities",
}

CATEGORY_ORDER = [
  "Internet", "Development", "Office", "Graphics", "Media",
  "Games", "Utilities", "System", "Education", "Science", "Other",
]

def config_load():
  """ read the user's config file or give them the default values """
  cfg = dict(CFG_DEFAULTS)

  if CONFIG_FILE.exists():
    try:
      with CONFIG_FILE.open("rb") as f:
        user = tomllib.load(f)

      # only adopt known keys; warn on unknown in case of mispellings
      for k, v in user.items():
        if k in CFG_DEFAULTS:
          cfg[k] = v

        else:
          print(f"[waydrawer] unknown config key: {k!r}", file=sys.stderr)

    except (OSError, tomllib.TOMLDecodeError) as e:
      print(f"[waydrawer] config error: {e}, using defaults", file=sys.stderr)

  return cfg

# load the user's config.toml for others to use
CFG = config_load()
