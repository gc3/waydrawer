from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("GioUnix", "2.0")
from gi.repository import GioUnix, Gtk, Gio, GLib, Gdk, Gtk4LayerShell as LayerShell

import json
import os
import re
import sys
import subprocess

from pathlib import Path
from urllib.parse import quote_plus

import waydrawer.cache  as cache
import waydrawer.config as config
from waydrawer.config import CATEGORY_MAP, CATEGORY_ORDER

from pprint import pprint # XXX gc3: FIXME

ICON_SIZE = 64
COLUMNS = 6
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 720

def _matches(app: GioUnix.DesktopAppInfo, q: str) -> bool:
    if not q:
        return True
    name = (app.get_display_name() or "").lower()
    generic = (app.get_generic_name() or "").lower()
    keywords = " ".join(app.get_keywords() or []).lower()
    return q in name or q in generic or q in keywords

# ---------- Launching ----------
def _launch_app(app: GioUnix.DesktopAppInfo) -> None:
    cmdline = app.get_commandline()
    if not cmdline:
        # DBusActivatable or no Exec= — fall back to GIO
        try:
            app.launch([], None)
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
        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as e:
        print(f"[waydrawer] launch failed: {e}", file=sys.stderr)

def _open_url(url: str) -> None:
    if not url.startswith(("http://", "https://", "file://")):
        url = "https://" + url

    subprocess.Popen(
        ["xdg-open", url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

def _web_search(query: str) -> None:
    _open_url(SEARCH_URL.format(quote_plus(query)))

def _looks_like_url(s: str) -> bool:
    s = s.strip()
    if not s or " " in s:
        return False

    if s.startswith(("http://", "https://", "file://")):
        return True

    return bool(re.match(r"^[\w.-]+\.[a-z]{2,}(/.*)?$", s, re.IGNORECASE))


# ---------- Widgets ----------
class AppTile(Gtk.Button):
    def __init__(self, app: GioUnix.DesktopAppInfo, drawer: "Drawer"):
        super().__init__()
        self.app = app
        self.drawer = drawer
        self.add_css_class("app-tile")
        self.set_has_frame(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_halign(Gtk.Align.CENTER)

        icon = Gtk.Image()
        gicon = app.get_icon()
        if gicon:
            icon.set_from_gicon(gicon)
        else:
            icon.set_from_icon_name("application-x-executable")
        icon.set_pixel_size(ICON_SIZE)
        box.append(icon)

        label = Gtk.Label(label=app.get_display_name() or "?")
        label.set_max_width_chars(14)
        label.set_ellipsize(3)
        label.set_justify(Gtk.Justification.CENTER)
        label.set_wrap(True)
        label.set_lines(2)
        box.append(label)

        self.set_child(box)
        self.connect("clicked", lambda _b: drawer._activate_app(self.app))

        # Right-click menu
        right_click = Gtk.GestureClick()
        right_click.set_button(Gdk.BUTTON_SECONDARY)
        right_click.connect("pressed", self._on_right_click)
        self.add_controller(right_click)

    def _on_right_click(self, _gesture, _n_press, x, y):
        app_id = self.app.get_id()
        is_fav = app_id in self.drawer.favorites

        menu = Gio.Menu()
        if is_fav:
          menu.append("Unpin from favorites", "win.toggle-favorite")
        else:
          menu.append("Pin to favorites", "win.toggle-favorite")

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(self)
        popover.set_position(Gtk.PositionType.BOTTOM)
        popover.set_pointing_to(Gdk.Rectangle(x=int(x), y=int(y), width=1, height=1))
        self.drawer._pending_favorite_toggle = app_id
        popover.popup()

# ---------- Widgets ----------
class Drawer(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title=config.APP_NAME)
        self.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)

        # make this an overlay
        LayerShell.init_for_window(self)
        LayerShell.set_namespace(self, config.APP_NAME)
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.EXCLUSIVE)

        # Make it a full-screen overlay
        for edge in (
            LayerShell.Edge.TOP,
            LayerShell.Edge.BOTTOM,
            LayerShell.Edge.LEFT,
            LayerShell.Edge.RIGHT,
        ):
            LayerShell.set_anchor(self, edge, True)

        # Optional: leave a margin so the drawer is centered with breathing room
        LayerShell.set_margin(self, LayerShell.Edge.TOP, 60)
        LayerShell.set_margin(self, LayerShell.Edge.BOTTOM, 60)
        LayerShell.set_margin(self, LayerShell.Edge.LEFT, 200)
        LayerShell.set_margin(self, LayerShell.Edge.RIGHT, 200)

        # load in all the app data from the .desktop files
        self.apps_by_category = dict(cache.load_apps())
        self.all_apps_by_id = {}
        for cat, apps in self.apps_by_category.items(): # apps = list of app dict
          for a in apps:                        # a = single app dict
            self.all_apps_by_id[a.id] = a

        self.favorites: list[str] = [
            i for i in load_favorites() if i in self.all_apps_by_id
        ]
        self._pending_favorite_toggle: str | None = None
        self._categories: list[tuple[str, Gtk.Label, Gtk.FlowBox]] = []
        self._current_query = ""

        # Action for the popover menu
        toggle_action = Gio.SimpleAction.new("toggle-favorite", None)
        toggle_action.connect("activate", self._on_toggle_favorite)
        self.add_action(toggle_action)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(24)
        root.set_margin_bottom(24)
        root.set_margin_start(28)
        root.set_margin_end(28)

        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search apps, type a URL, or query the web…")
        self.search.connect("search-changed", self._on_search_changed)
        self.search.connect("activate", self._on_search_activate)
        root.append(self.search)


        self.web_row = Gtk.Button()
        self.web_row.add_css_class("web-fallback")
        self.web_row.set_visible(False)
        self.web_row.connect("clicked", self._on_web_clicked)
        root.append(self.web_row)

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.grid_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)

        # Favorites row (above categories)
        self.fav_header = Gtk.Label(label="Favorites", xalign=0)
        self.fav_header.add_css_class("category-header")
        self.fav_flow = Gtk.FlowBox()
        self.fav_flow.set_max_children_per_line(COLUMNS)
        self.fav_flow.set_min_children_per_line(1)
        self.fav_flow.set_homogeneous(True)
        self.fav_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.fav_flow.set_column_spacing(6)
        self.fav_flow.set_row_spacing(10)
        self.grid_box.append(self.fav_header)
        self.grid_box.append(self.fav_flow)
        self._rebuild_favorites_row()

        for cat in CATEGORY_ORDER:
            apps = self.apps_by_category.get(cat, [])
            if not apps:
                continue
            header = Gtk.Label(label=cat, xalign=0)
            header.add_css_class("category-header")
            self.grid_box.append(header)

            flow = Gtk.FlowBox()
            flow.set_max_children_per_line(COLUMNS)
            flow.set_min_children_per_line(1)
            flow.set_homogeneous(True)
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_column_spacing(6)
            flow.set_row_spacing(10)
            for ai in apps:
                flow.append(AppTile(ai, self))
            self.grid_box.append(flow)
            self._categories.append((cat, header, flow))

        scroller.set_child(self.grid_box)
        root.append(scroller)
        self.set_child(root)

        # send key presses to the window from the input
        kc = Gtk.EventControllerKey()
        kc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        kc.connect("key-pressed", self._on_key_pressed)
        self.add_controller(kc)

    def _rebuild_favorites_row(self):
        # Clear existing tiles
        child = self.fav_flow.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.fav_flow.remove(child)
            child = nxt

        if not self.favorites:
            self.fav_header.set_visible(False)
            self.fav_flow.set_visible(False)
            return

        self.fav_header.set_visible(True)
        self.fav_flow.set_visible(True)
        for app_id in self.favorites:
            app = self.all_apps_by_id.get(app_id)
            if app:
                self.fav_flow.append(AppTile(app, self))

    def _on_toggle_favorite(self, _action, _param):
        app_id = self._pending_favorite_toggle
        self._pending_favorite_toggle = None
        if not app_id:
            return
        if app_id in self.favorites:
            self.favorites.remove(app_id)
        else:
            self.favorites.append(app_id)
        save_favorites(self.favorites)
        self._rebuild_favorites_row()

    # ----- handlers -----
    def _on_key_pressed(self, _kc, keyval, _kc2, _state):
        if keyval == Gdk.KEY_Escape:
            self.get_application().quit()
            return True

        return False

    def _activate_app(self, app: GioUnix.DesktopAppInfo):
        _launch_app(app)
        self.get_application().quit()

    def _on_search_changed(self, entry: Gtk.SearchEntry):
        q = entry.get_text().strip().lower()
        self._current_query = q

        # Hide favorites row when searching
        searching = bool(q)
        if not searching and self.favorites:
            self.fav_header.set_visible(True)
            self.fav_flow.set_visible(True)
        else:
            self.fav_header.set_visible(False)
            self.fav_flow.set_visible(False)

        if not q:
            for _, header, flow in self._categories:
                header.set_visible(True)
                flow.set_visible(True)
                flow.set_filter_func(None)
            self.web_row.set_visible(False)
            return

        any_visible = False
        for cat, header, flow in self._categories:
            apps = self.apps_by_category.get(cat, [])
            has_match = any(_matches(a, q) for a in apps)
            header.set_visible(has_match)
            flow.set_visible(has_match)
            if has_match:
                any_visible = True
                flow.set_filter_func(
                    lambda child, qq=q: _matches(child.get_child().app, qq)
                )
                flow.invalidate_filter()

        if any_visible:
            self.web_row.set_visible(False)
        else:
            raw = entry.get_text().strip()
            if _looks_like_url(raw):
                self.web_row.set_label(f"  Open  {raw}")
            else:
                self.web_row.set_label(f"  Search the web for  \u201c{raw}\u201d")
            self.web_row.set_visible(True)

    def _first_visible_app(self):
        q = self._current_query
        if not q:
            return None
        for cat, _h, _flow in self._categories:
            for app in self.apps_by_category.get(cat, []):
                if _matches(app, q):
                    return app
        return None

    def _on_search_activate(self, entry: Gtk.SearchEntry):
        raw = entry.get_text().strip()
        if not raw:
            return
        self._current_query = raw.lower()  # sync before lookup
        app = self._first_visible_app()
        if app:
            self._activate_app(app)
            return
        if _looks_like_url(raw):
            _open_url(raw)
        else:
            _web_search(raw)
        self.get_application().quit()

    def _on_web_clicked(self, _btn):
        raw = self.search.get_text().strip()
        if not raw:
            return
        if _looks_like_url(raw):
            _open_url(raw)
        else:
            _web_search(raw)
        self.get_application().quit()

# ---------- Styling ----------
# XXX gc3: FIXME comments and own file pls
CSS = b"""
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

def setup_CSS() -> None:
  provider = Gtk.CssProvider()
  if hasattr(provider, "load_from_string"):
    provider.load_from_string(CSS.decode())

  else:
    provider.load_from_data(CSS, -1)

  Gtk.StyleContext.add_provider_for_display(
    Gdk.Display.get_default(),
    provider,
    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
  )


# ---------- Favorites ----------
# XXX gc3: FIXME comments and own file pls
FAVORITES_FILE = config.CONFIG_DIR / "favorites.json"

def load_favorites() -> list[str]:
    try:
        return json.loads(FAVORITES_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_favorites(ids: list[str]) -> None:
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    FAVORITES_FILE.write_text(json.dumps(ids, indent=2))


