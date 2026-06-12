# ----------- Styling ----------------------------------------------------------
"""
  Here we handle both CSS including loading the style.css file from the config
  directory or providing a default.
"""
from __future__ import annotations

import sys

# pylint: disable=wrong-import-position
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib

from waydrawer.config import CONFIG_DIR

USER_CSS_FILE = CONFIG_DIR / "style.css"

DEFAULT_CSS = b"""
window { background-color: rgba(20, 22, 28, 0.94); }

entry {
  font-size: 16px;
  padding: 12px;
  border-radius: 10px;
  background-color: transparent;
  color: #eee;
  caret-color: #cce;
}
entry:focus { background-color: rgba(255,255,255,0.10); }

.category-header {
  font-size: 12px;
  font-weight: 700;
  color: #99a;
  letter-spacing: 0.08em;
  margin-top: 6px;
  margin-bottom: 2px;
}

.app-tile {
  padding: 10px;
  border-radius: 12px;
  background: transparent;
  border: none;
}
.app-tile:hover  { background-color: rgba(255,255,255,0.07); }
.app-tile:active { background-color: rgba(255,255,255,0.12); }
.app-tile label  { color: #e6e6ec; font-size: 12px; }

.web-fallback {
  padding: 12px;
  border-radius: 10px;
  background-color: rgba(120, 160, 255, 0.10);
  color: #cfd8ff;
  border: none;
}
.web-fallback:hover { background-color: rgba(120, 160, 255, 0.18); }

scrollbar { background: transparent; }
scrollbar slider { background-color: rgba(255,255,255,0.18); border-radius: 6px; }
"""


def setup_css() -> None:
  """ load the css from the users style.css or get the default """

  if USER_CSS_FILE.exists():
    # user CSS override (loaded at PRIORITY_USER so it stacks on top of defaults)
    try:
      user_provider = Gtk.CssProvider()
      user_provider.load_from_path(str(USER_CSS_FILE))
      Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        user_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_USER,
      )

    except GLib.Error as e:
      print(f"[waydrawer] user css error: {e}", file=sys.stderr)

  else:
    # default CSS used if there's no user file
    provider = Gtk.CssProvider()
    if hasattr(provider, "load_from_string"):
      provider.load_from_string(DEFAULT_CSS.decode())

    else:
      provider.load_from_data(DEFAULT_CSS, -1)

    Gtk.StyleContext.add_provider_for_display(
      Gdk.Display.get_default(),
      provider,
      Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
