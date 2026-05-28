# ----------- User Interface for waydrawer -------------------------------------
#
# Using Gtk, we build the needed widgets and helpers to define the UI. The
# handling of styling from the config files is done in style.py and applied in
# main()
#
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
from urllib.parse import quote_plus

import waydrawer.cache      as cache
import waydrawer.config     as config
import waydrawer.favorites  as favs

from waydrawer.math import try_math
from waydrawer.config import CATEGORY_MAP, CATEGORY_ORDER

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
# XXX gc3: FIXME comments in here and spacing ...
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
    _open_url(config.SEARCH_URL.format(quote_plus(query)))

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


    # NB: Direct toggle (no menu) because popovers don't route input correctly
    # through gtk4-layer-shell on this stack, so we skip the confirmation step.
    def _on_right_click(self, _gesture, _n_press, x, y):
        app_id = self.app.get_id()
        if app_id in self.drawer.favorites:
            self.drawer.favorites.remove(app_id)
        else:
            self.drawer.favorites.append(app_id)
        favs.save_favorites(self.drawer.favorites)
        self.drawer._rebuild_favorites_row()
    """
    def _on_right_click(self, _gesture, _n_press, x, y):
        app_id = self.app.get_id()
        is_fav = app_id in self.drawer.favorites

        menu = Gio.Menu()
        if is_fav:
          menu.append("Unpin from favorites", "win.toggle-favorite")
        else:
          menu.append("Pin to favorites", "win.toggle-favorite")

        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(self)
        popover.set_position(Gtk.PositionType.BOTTOM)
        popover.set_pointing_to(rect)
        self.drawer._pending_favorite_toggle = app_id
        popover.popup()
    """

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
            i for i in favs.load_favorites() if i in self.all_apps_by_id
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
        favs.save_favorites(self.favorites)
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
            result = try_math(raw)
            if result is not None:
              self.web_row.set_label(f"  Math result is {result}")

            elif _looks_like_url(raw):
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
        """ Handler for hitting enter in the search bar"""
        raw = entry.get_text().strip()
        if not raw:
            return

        self._current_query = raw.lower()  # sync before lookup

        if (result := try_math(raw)) is not None:
          clipboard = Gdk.Display.get_default().get_clipboard()
          clipboard.set(result)
          self.web_row.set_label(f"  Math result is copied to clipboard!")
          return

        if (app := self._first_visible_app()) is not None:
          self._activate_app(app)

        elif _looks_like_url(raw):
          _open_url(raw)

        else:
          _web_search(raw)

        self.get_application().quit()

    def _on_web_clicked(self, _btn):
        """ Handler for clicking the button at the bottom of the results"""
        raw = self.search.get_text().strip()
        if not raw:
          return

        if (result  := try_math(raw)) is not None:
          clipboard = Gdk.Display.get_default().get_clipboard()
          clipboard.set(result)
          self.web_row.set_label(f"  Math result is copied to clipboard!")
          return

        if _looks_like_url(raw):
          _open_url(raw)

        else:
          _web_search(raw)

        self.get_application().quit()
