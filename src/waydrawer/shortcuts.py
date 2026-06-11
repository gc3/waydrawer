# ----------- Shortcuts -------------------------------------------------------
"""
  User-defined name -> target shortcuts. Each target is handed to xdg-open.
  Stored as a [shortcuts] table in shortcuts.toml in the config dir, e.g.:

    # name = "target"  (each target is handed to xdg-open)

    [shortcuts]
    notes = "/home/gc3/Documents/notes.md"
    downloads = "/home/gc3/Downloads"

  The file is hand-editable and also written by the settings UI; comments and
  formatting are preserved across UI edits.
"""
from __future__ import annotations

import sys
import tomlkit

from waydrawer.config import CONFIG_DIR


TABLE = "shortcuts"
SHORTCUTS_FILE = CONFIG_DIR / "shortcuts.toml"


# ----------- API -------------------------------------------------------------
def load() -> dict[str, str]:
  """
    Load name -> target shortcuts
    run. Defensive: only string -> string survives.
  """
  try:
    with SHORTCUTS_FILE.open("r", encoding="utf-8") as f:
      data = tomlkit.load(f).unwrap().get(TABLE, {})

  except (OSError, tomlkit.exceptions.ParseError):
    return {}

  # be defensive about hand-edited files: keep only string -> string
  if not isinstance(data, dict):
    return {}

  return {str(k): str(v) for k, v in data.items()}

def save(name: str, target: str) -> None:
  """
    Add or update a single shortcut, preserving comments/formatting on disk.
  """
  doc = _read()
  if TABLE not in doc:
    doc[TABLE] = tomlkit.table()

  doc[TABLE][name] = target
  _write(doc)

def delete(name: str) -> None:
  """
    Remove a shortcut by name. No-op if it isn't present.
  """
  doc = _read()
  table = doc.get(TABLE)
  if table is not None and name in table:
    del table[name]
    _write(doc)

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


# ----------- Internal Helpers ----------------------------------------------------
def _read():
  """
    shortcuts.toml as a tomlkit document (comments intact), or a fresh document
    with an empty [shortcuts] table if the file is missing or unparseable.
  """
  if SHORTCUTS_FILE.exists():
    try:
      with SHORTCUTS_FILE.open("r", encoding="utf-8") as f:
        return tomlkit.load(f)

    except (OSError, tomlkit.exceptions.ParseError) as e:
      print(f"[waydrawer] shortcuts read error: {e}, rewriting empty",
            file=sys.stderr)

  # without an existing file, we make an empty new one for the user
  doc = tomlkit.document()
  doc.add(tomlkit.comment('name = "target"  (each target is handed to xdg-open)'))
  doc[TABLE] = tomlkit.table()
  return doc

def _write(doc) -> None:
  """
    atomically-ish dump a tomlkit doc to shortcuts.toml
  """
  CONFIG_DIR.mkdir(parents=True, exist_ok=True)
  with SHORTCUTS_FILE.open("w", encoding="utf-8") as f:
    tomlkit.dump(doc, f)
