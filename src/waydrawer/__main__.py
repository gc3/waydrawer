# ----------- waydraw Main App -------------------------------------------------
# waydrawer: GTK4 app drawer for Wayland.
#
# Features:
#   - Reads .desktop files via Gio.AppInfo (uses your system icon theme)
#   - Apps grouped by category (Internet, Development, Office, Media, etc.)
#   - Live filter as you type (matches name, generic name, keywords)
#   - Web search fallback when no apps match (Enter or click the row)
#   - URL loading in browser if the input looks like a URL
#   - Executes basic arithmetic in the search bar & copies results to clipboard
#   - Layer-shell overlay; Esc to close, Enter to launch first visible match
#
# Dependencies:
#   python-gobject gtk4 gtk4-layer-shell
#
# Install:
#   make install
#
# Hyprland hyprlang keybind:
#   bind = SUPER, Space, exec, waydrawer
#
# Hyprland lua keybind:
#   hl.bind("SUPER + Space", hl.dsp.exec_cmd("waydrawer"))
#
# Configuration:
#   ~/.config/waydrawer/config.toml
#   ~/.config/waydrawer/style.css
#
from __future__ import annotations

import os
import sys
import fcntl

import waydrawer.ui     as ui
import waydrawer.style  as style

from pathlib import Path
from gi.repository import GLib, Gtk, Gio


# XXX: The dynamic linker needs to load libgtk4-layer-shell.so before libwayland-client.so.
#
#   This moves gtk4-layer-shell before libwayland-client in the linker options.
#   See https://github.com/wmww/gtk4-layer-shell/blob/main/linking.md for more info
#
_PRELOAD = "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so"
if os.path.exists(_PRELOAD) and "gtk4-layer-shell" not in os.environ.get("LD_PRELOAD", ""):
  os.environ["LD_PRELOAD"] = _PRELOAD
  os.environ["PYTHONPATH"] = ":".join(sys.path)  # ← carry path into new process
  os.execv(sys.executable, [sys.executable] + sys.argv)


class DrawerApp(Gtk.Application):
  def __init__(self):
    super().__init__(
      application_id = "org.local.waydrawer",
      flags = Gio.ApplicationFlags.NON_UNIQUE,
    )

  def do_activate(self):
    style.setup_CSS()

    win = ui.Drawer(self)
    win.present()
    GLib.idle_add(win.search.grab_focus)

def main():
  # we only want 1 instance of this app running at a time
  lock_fd = open(f"/run/user/{os.getuid()}/waydrawer.lock", "w")
  try:
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

  except BlockingIOError:
    print(APP_NAME + " already running. Exiting...")
    sys.exit(0)

  return DrawerApp().run(sys.argv)


# we like to run it, run it
if __name__ == "__main__":
    sys.exit(main())
