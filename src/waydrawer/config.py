# ----------- Config ----------------------------------------------------------
"""
  Read the user's config file in ~/.config/waydrawer/config.toml or give them
  the default values listed below if there's no file. This will ignore unknown
  keys in the config file but give a warning for unknown keys.
"""
from __future__ import annotations

import sys
from pathlib import Path

import tomlkit

from gi.repository import GLib

APP_NAME = "waydrawer"
CONFIG_DIR = Path(GLib.get_user_config_dir()) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.toml"

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


# ----------- API -------------------------------------------------------------
def load():
  """ read the user's config file or give them the default values """
  cfg = dict(CFG_DEFAULTS)

  if CONFIG_FILE.exists():
    try:
      with CONFIG_FILE.open("r", encoding="utf-8") as f:
        user = tomlkit.load(f).unwrap()

      # only adopt known keys with the right type; warn otherwise.
      # NB: bool is an int subclass, so an exact type match is required.
      for k, v in user.items():
        if k not in CFG_DEFAULTS:
          print(f"[waydrawer] unknown config key: {k!r}", file=sys.stderr)

        elif type(v) is not type(CFG_DEFAULTS[k]):
          print(
            f"[waydrawer] config key {k!r}: expected "
            f"{type(CFG_DEFAULTS[k]).__name__}, got {type(v).__name__}; "
            "using default",
            file=sys.stderr,
          )

        else:
          cfg[k] = v

    except (OSError, tomlkit.exceptions.ParseError) as e:
      print(f"[waydrawer] config error: {e}, using defaults", file=sys.stderr)

  return cfg

def save(key, value):
  """
    Set a single config key on disk, preserving any comments/formatting the
    user has in config.toml, and keep the in-memory CFG in sync.
  """
  if key not in CFG_DEFAULTS:
    raise KeyError(f"unknown config key: {key!r}")

  doc = _config_doc()
  doc[key] = value

  CONFIG_DIR.mkdir(parents=True, exist_ok=True)
  with CONFIG_FILE.open("w", encoding="utf-8") as f:
    tomlkit.dump(doc, f)

  CFG[key] = value


# ----------- Internal Helpers ----------------------------------------------------
def _config_doc():
  """
    Return the existing config.toml as a tomlkit document (comments and
    formatting intact), or a fresh document seeded with the defaults if the
    file is missing or unparseable.
  """
  if CONFIG_FILE.exists():
    try:
      with CONFIG_FILE.open("r", encoding="utf-8") as f:
        return tomlkit.load(f)

    except (OSError, tomlkit.exceptions.ParseError) as e:
      print(f"[waydrawer] config read error: {e}, rewriting from defaults",
            file=sys.stderr)

  doc = tomlkit.document()
  for k, v in CFG_DEFAULTS.items():
    doc[k] = v

  return doc

# ----------- LOAD EXTERNAL FILE --------------------------------------------------
CFG = load()
