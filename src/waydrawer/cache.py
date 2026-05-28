# ----------- AppInfo Cache -------------------------------------------------------
#
# Loading the Gio.AppInfo files from disk is one of the slowest operations
# Waydrawer does, so we manage caching the results of reading all the .desktop files
# here.
#
from __future__ import annotations

import json
import sys

from pathlib import Path
from gi.repository import GLib, Gio

from waydrawer.app import App
from waydrawer.config import CATEGORY_MAP, CATEGORY_ORDER

# ----------- Constants -----------------------------------------------------------
CACHE_DIR = Path(GLib.get_user_cache_dir()) / "waydrawer"
APPS_CACHE = CACHE_DIR / "apps.json"
CACHE_VERSION = 3  # bump if you change the schema


# ----------- Internal Helpers ----------------------------------------------------
def _app_dirs():
  """
    Gather all the directories containing .desktop files
  """
  dirs = [Path(d) / "applications" for d in GLib.get_system_data_dirs()]
  dirs.append(Path(GLib.get_user_data_dir()) / "applications")
  return [d for d in dirs if d.is_dir()]

def _serialize(info):
  """
    Given a Gio.AppInfo, return one of our app wrappers. We use this as a layer
    of indirection to callers so whether we load from cache or from Gio, they
    see the same interface.
  """
  return App(
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


# ----------- API -------------------------------------------------------------
def load_apps():
  """
    Returns dict of {category => [App, ...]} where categories point to a list of
    apps in that category. Apps are sorted alphabetically.
  """

  # Max mtime across XDG application dirs. One stat per dir.
  mtime = max((d.stat().st_mtime for d in _app_dirs()), default=0)
  if APPS_CACHE.exists():
    try:
      cached = json.loads(APPS_CACHE.read_text())
      if cached.get("v") == CACHE_VERSION and cached.get("mtime") == mtime:
        # * HIT *
        #   rehydrate dicts -> App instances and return
        result = []
        for cat, apps in cached["sections"]:
          rehydrated = [App.from_dict(d) for d in apps]
          result.append([cat, rehydrated])
        return result

    except Exception as e:
      print(f"[waydrawer] cache read error: {e}", file=sys.stderr)

  # * MISS *
  #   reload all the app infos and then have them sorted
  raw_apps = [
    _serialize(a) for a in Gio.AppInfo.get_all()
    if isinstance(a, Gio.DesktopAppInfo) and not a.get_nodisplay()
  ]
  sections = _categorize(raw_apps)

  #   serialize App -> dict for JSON and write them to the cache
  CACHE_DIR.mkdir(parents=True, exist_ok=True)
  APPS_CACHE.write_text(json.dumps({
    "v": CACHE_VERSION,
    "mtime": mtime,
    "sections": [[cat, [a.to_dict() for a in apps]] for cat, apps in sections],
  }))

  return sections
