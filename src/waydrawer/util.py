# ----------- Utils -----------------------------------------------------------
"""
  Dumping ground for commonly used utility functions across the app.
"""
from __future__ import annotations

import re
import os
import sys
import subprocess
from urllib.parse import quote_plus

# pylint: disable=wrong-import-position
import gi
gi.require_version("Gdk", "4.0")
gi.require_version("GioUnix", "2.0")
from gi.repository import Gdk, Gio, GioUnix, GLib

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
def launch_app(ai) -> None:
  """
    Launch the app represented by the given app info (our cached facade).

    Gio handles the .desktop fine print for us: field-code expansion (%f, %u,
    %%, embedded forms like --file=%f), Path= working dir, and Terminal=true.
    The context undoes our env injection and provides an xdg-activation token
    so the new window actually gets focus on Wayland.
  """
  try:
    ai.launch([], _launch_ctx())

  except GLib.Error as e:
    print(f"[waydrawer] launch failed: {e}", file=sys.stderr)


def _launch_ctx() -> Gio.AppLaunchContext:
  """
    Launch context for child apps. Prefer the Gdk one (carries an
    xdg-activation focus token on Wayland); fall back to plain Gio if no
    display. Either way, scrub the re-exec env injection (see child_env).
  """
  display = Gdk.Display.get_default()
  ctx = display.get_app_launch_context() if display else Gio.AppLaunchContext()
  env = child_env()

  for var in ("LD_PRELOAD", "PYTHONPATH"):
    ctx.unsetenv(f"_WAYDRAWER_ORIG_{var}") # undo our temp saves for the kids
    if var in env:
      ctx.setenv(var, env[var])

    else:
      ctx.unsetenv(var)

  return ctx

def child_env() -> dict[str, str]:
  """
    Environment for spawned children: undo the LD_PRELOAD / PYTHONPATH
    injection done by the re-exec in __main__, restoring pre-exec values.
  """
  env = dict(os.environ)
  for var in ("LD_PRELOAD", "PYTHONPATH"):
    orig = env.pop(f"_WAYDRAWER_ORIG_{var}", None)
    if orig:
      env[var] = orig

    elif orig is not None:        # stash exists but was empty -> var was unset
      env.pop(var, None)

  return env

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
    Gio.AppInfo.launch_default_for_uri(uri, _launch_ctx())

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
    env=child_env(),
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
    close_fds=True,
  )
