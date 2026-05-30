# ----------- waydraw Main App -------------------------------------------------
"""
  waydrawer: GTK4 app drawer for Wayland
"""
from __future__ import annotations

import os
import sys
import fcntl

# pylint: disable=wrong-import-position
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("GioUnix", "2.0")
from gi.repository import GLib, Gtk, Gio, Gtk4LayerShell as LayerShell

from waydrawer import ui
from waydrawer import style

#
# NB: The dynamic linker needs to load libgtk4-layer-shell.so before libwayland-client.so.
#
#   This moves gtk4-layer-shell before libwayland-client in the linker options.
#   See https://github.com/wmww/gtk4-layer-shell/blob/main/linking.md for more info
#
_PRELOAD = "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so"
if os.path.exists(_PRELOAD) and "gtk4-layer-shell" not in os.environ.get("LD_PRELOAD", ""):
  os.environ["LD_PRELOAD"] = _PRELOAD
  os.environ["PYTHONPATH"] = ":".join(sys.path)  # ← carry path into new process
  os.execv(sys.executable, [sys.executable] + sys.argv)


class WayDrawerApp(Gtk.Application):
  """ main Gtk application """
  def __init__(self):
    super().__init__(
      application_id = "org.local.waydrawer",
      flags = Gio.ApplicationFlags.NON_UNIQUE,
    )

  def do_activate(self):  # pylint: disable=arguments-differ
    """ initialize the app with css and then draw the window """

    # we expect to run as a layer
    if not LayerShell.is_supported():
      print(
        "[waydrawer] this compositor does not support wlr-layer-shell; "
        "waydrawer requires a wlroots-based compositor (Sway, Hyprland, niri, …).",
        file=sys.stderr,
      )
      sys.exit(1)

    # load the user's css or the default
    style.setup_css()

    # open da window
    win = ui.Drawer(self)
    win.present()
    GLib.idle_add(win.search.grab_focus)

def main():
  """ Is ya man,  """

  # on da flo'?
  #   we only want 1 instance of this app running at a time
  #   pylint: disable=consider-using-with
  lock_fd = open(f"/run/user/{os.getuid()}/waydrawer.lock", "wb")
  try:
    # if he aint
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

  except BlockingIOError:
    # lemme know
    print("[waydrawer] already running. Exiting...")
    sys.exit(0)

  # Let me see if you can run it, run it
  return WayDrawerApp().run(sys.argv)

# indeed I can run it, run it
if __name__ == "__main__":
  sys.exit(main())
