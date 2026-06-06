# ----------- Shortcuts -------------------------------------------------------
"""
  User-defined name -> target shortcuts. Each target is handed to xdg-open.
  Stored as a JSON object in the config dir.

  e.g.:
  {
    "notes": "/home/gc3/Documents/notes.md",
    "downloads": "/home/gc3/Downloads",
    "docs": "/home/gc3/Documents"
  }

  XXX: there is no in-app editor, the file is the source of truth.
"""
from __future__ import annotations

import json
from waydrawer.config import CONFIG_DIR

SHORTCUTS_FILE = CONFIG_DIR / "shortcuts.json"

def load() -> dict[str, str]:
  """
    Load name -> target shortcuts from the config directory
  """
  try:
    data = json.loads(SHORTCUTS_FILE.read_text())

  except (FileNotFoundError, json.JSONDecodeError):
    return {}

  # be defensive about hand-edited files: keep only string -> string
  if not isinstance(data, dict):
    return {}

  return {str(k): str(v) for k, v in data.items()}


def match(scs: dict[str, str], q: str, exact: bool) -> tuple[str, str] | None:
  """
    Resolve a query to a shortcut. An exact (case-insensitive) name match
    always wins; if exact is False, fall back to the first name the query is
    a prefix of, in file order. Returns (name, target) or None.
  """
  q = q.strip().lower()
  if not q:
    return None

  prefix = None
  for name, target in scs.items():
    nl = name.lower()
    if nl == q:
      return (name, target)

    if not exact and prefix is None and nl.startswith(q):
      prefix = (name, target)

  return prefix
