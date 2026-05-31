# ----------- AppInfo Cache -------------------------------------------------------
"""
  Loading the Gio.AppInfo files from disk is one of the slowest operations
  Waydrawer does, so we manage caching the results of reading all the .desktop files
  here.
"""
from __future__ import annotations

import json
import sys

from pathlib import Path
from gi.repository import GLib, Gio

from waydrawer.app_info import AppInfo
from waydrawer.config import CATEGORY_MAP, CATEGORY_ORDER

# ----------- Constants -----------------------------------------------------------
CACHE_DIR = Path(GLib.get_user_cache_dir()) / "waydrawer"
APPS_CACHE = CACHE_DIR / "apps.json"
CACHE_VERSION = 3  # bump if you change the schema


# ----------- Internal Helpers ----------------------------------------------------
def _serialize(info):
  """
    Given a Gio.AppInfo, return one of our app wrappers. We use this as a layer
    of indirection to callers so whether we load from cache or from Gio, they
    see the same interface.
  """
  return AppInfo (
    id = info.get_id(),
    filename = info.get_filename(),
    name = info.get_display_name(),
    generic_name=info.get_generic_name() or "",
    comment = info.get_description() or "",
    icon = info.get_string("Icon") or "",
    commandline = info.get_commandline() or "",
    categories = [c for c in (info.get_categories() or "").split(";") if c],
    keywords = [k for k in (info.get_string("Keywords") or "").split(";") if k],
  )

def _categorize(apps):
  """
    Put the given apps into their respective categories and the sort the
    categories alphabetically by name
  """

  # put every app into its category buckets
  buckets = {cat: [] for cat in CATEGORY_ORDER}
  for app in apps:
    cat = next(
      (CATEGORY_MAP[c] for c in app.categories if c in CATEGORY_MAP),
      "Other",
    )
    buckets[cat].append(app)

  # sort by alpha
  for cat in buckets:
    buckets[cat].sort(key=lambda a: a.name.casefold())

  # JSON has no tuples — store as list of [cat, apps] pairs
  return [[cat, buckets[cat]] for cat in CATEGORY_ORDER if buckets[cat]]

def _app_dirs():
  """
    Directories containing .desktop files: the XDG data dirs plus the flatpak
    export dirs explicitly, in case the latter aren't in XDG_DATA_DIRS (e.g.
    launched outside a full login session). Deduped, real dirs only.
  """
  user_data = Path(GLib.get_user_data_dir())
  dirs = [Path(d) / "applications" for d in GLib.get_system_data_dirs()]
  dirs.append(user_data / "applications")
  dirs.append(user_data / "flatpak/exports/share/applications")
  dirs.append(Path("/var/lib/flatpak/exports/share/applications"))

  seen, out = set(), []
  for d in dirs:
    if d not in seen and d.is_dir():
      seen.add(d)
      out.append(d)
  return out

def _max_mtime():
  """
    Newest mtime across the app dirs *and* the .desktop files in them. Dir
    mtimes catch adds/removals (the entry list changes); file mtimes catch
    in-place content edits, which do NOT bump the dir mtime. We need both.
  """
  dirs = _app_dirs()
  m = max((d.stat().st_mtime for d in dirs), default=0.0)
  for d in dirs:
    for file in d.glob("*.desktop"):
      try:
        m = max(m, file.stat().st_mtime)
      except OSError:
        pass

  return m

# ----------- API -------------------------------------------------------------
def load_apps():
  """
    Returns dict of {category => [AppInfo, ...]} where categories point to a list of
    apps in that category. Apps are sorted alphabetically.
  """
  mtime = _max_mtime()
  if APPS_CACHE.exists():
    try:
      cached = json.loads(APPS_CACHE.read_text())
      if cached.get("v") == CACHE_VERSION and cached.get("mtime") == mtime:
        # * HIT *
        #   rehydrate dicts -> AppInfo instances and return
        result = []
        for cat, apps in cached["sections"]:
          rehydrated = [AppInfo.from_dict(d) for d in apps]
          result.append([cat, rehydrated])
        return result

    except (OSError, ValueError, KeyError, TypeError) as e:
      print(f"[waydrawer] cache read error: {e}", file=sys.stderr)

  # * MISS *
  #   reload all the app infos and then have them sorted
  raw_apps = [
    _serialize(a) for a in Gio.AppInfo.get_all()
    if isinstance(a, Gio.DesktopAppInfo) and not a.get_nodisplay()
  ]
  sections = _categorize(raw_apps)

  #   serialize AppInfo -> dict for JSON and write them to the cache
  CACHE_DIR.mkdir(parents=True, exist_ok=True)
  APPS_CACHE.write_text(json.dumps({
    "v": CACHE_VERSION,
    "mtime": mtime,
    "sections": [[cat, [a.to_dict() for a in apps]] for cat, apps in sections],
  }))

  return sections
