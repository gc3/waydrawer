# ----------- Utils -----------------------------------------------------------
"""
  Dumping ground for commonly used utility functions across the app.
"""
from __future__ import annotations

import re
import sys
import subprocess
from urllib.parse import quote_plus

# pylint: disable=wrong-import-position
import gi
gi.require_version("GioUnix", "2.0")
from gi.repository import Gio, GioUnix, GLib

from waydrawer.config import CFG


# ----------- Strings ---------------------------------------------------------
def matches(app_info: GioUnix.DesktopAppInfo, q: str) -> bool:
  """
    Given some app info and a query, return true if they match.
  """
  if not q:
    return True

  name = (app_info.get_display_name() or "").lower()
  generic = (app_info.get_generic_name() or "").lower()
  keywords = " ".join(app_info.get_keywords() or []).lower()
  return q in name or q in generic or q in keywords

def looks_like_url(s: str) -> bool:
  """
    Return true if the given string looks like a URL
  """
  s = s.strip()
  if not s or " " in s:
    return False

  if s.startswith(("http://", "https://", "file://")):
    return True

  return bool(re.match(r"^[\w.-]+\.[a-z]{2,}(/.*)?$", s, re.IGNORECASE))


# ----------- Process/App Launching -------------------------------------------
def launch_app(ai: GioUnix.DesktopAppInfo) -> None:
  """
    Launch the app represented by the given app info.
  """
  cmdline = ai.get_commandline()
  if not cmdline:
    # DBusActivatable or no Exec= — fall back to GIO
    try:
      ai.launch([], None)

    except GLib.Error as e:
      print(f"[waydrawer] launch failed: {e}", file=sys.stderr)
    return

  try:
    _ok, argv = GLib.shell_parse_argv(cmdline)

  except GLib.Error as e:
    print(f"[waydrawer] failed to parse Exec=: {e}", file=sys.stderr)
    return

  # Strip .desktop field codes (%f %F %u %U %i %c %k ...)
  argv = [a for a in argv if not (len(a) == 2 and a.startswith("%"))]
  try:
    spawn_detached(argv)

  except OSError as e:
    print(f"[waydrawer] launch failed: {e}", file=sys.stderr)

def open_target(target: str) -> None:
  """
    Used primarily for shortcuts, this opens target with the user's registered
    default handler.

    Prefer the in-process GLib path: no external binary, and it honors
    Terminal=true so terminal apps (vim, …) get a real terminal. Fall back to
    xdg-open only when GLib has no default registered for the target.
  """
  try:
    uri = Gio.File.new_for_commandline_arg(target).get_uri()
    Gio.AppInfo.launch_default_for_uri(uri, None)

  except GLib.Error:
    spawn_detached(["xdg-open", target])

def web_search(query: str) -> None:
  """
    Pass the given query to the configured search website.
  """
  open_url(CFG["search_url"].format(quote_plus(query)))

def open_url(url: str) -> None:
  """
    Given a url, open it in the default browser
  """
  if not url.startswith(("http://", "https://", "file://")):
    url = "https://" + url

  spawn_detached(["xdg-open", url])

def spawn_detached(argv: list[str]) -> None:
  """
    Launch the given process defined by argv as a totall disconnected process
    from waydrawer so their futures aren't intertwined.
  """
  subprocess.Popen(   # pylint: disable=consider-using-with
    argv,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
    close_fds=True,
  )
