# ----------- User Interface for waydrawer -------------------------------------
"""
  Using Gtk, we build the needed widgets and helpers to define the UI. The
  handling of styling from the config files is done in style.py and applied in
  main()
"""
from __future__ import annotations

import re
import sys
import shutil
import subprocess
from urllib.parse import quote_plus

# pylint: disable=wrong-import-position
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("GioUnix", "2.0")
from gi.repository import GioUnix, Gtk, GLib, Gdk, Gtk4LayerShell as LayerShell

from waydrawer import cache
from waydrawer import config
from waydrawer import favorites
from waydrawer import math

# load the user's config.toml
CFG = config.config_load()


# ----------- Helper Functions -------------------------------------------------
def _matches(app_info: GioUnix.DesktopAppInfo, q: str) -> bool:
  if not q:
    return True

  name = (app_info.get_display_name() or "").lower()
  generic = (app_info.get_generic_name() or "").lower()
  keywords = " ".join(app_info.get_keywords() or []).lower()
  return q in name or q in generic or q in keywords

def _launch_app_and_exit(ai: GioUnix.DesktopAppInfo, drawer: "Drawer") -> None:

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
    subprocess.Popen(  # pylint: disable=consider-using-with
      argv,
      stdin=subprocess.DEVNULL,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      start_new_session=True,
      close_fds=True,
    )

  except OSError as e:
    print(f"[waydrawer] launch failed: {e}", file=sys.stderr)

  # 'exit' the app after loading an external program
  drawer.get_application().dismiss()


def _open_url(url: str) -> None:
  if not url.startswith(("http://", "https://", "file://")):
    url = "https://" + url

  subprocess.Popen(   # pylint: disable=consider-using-with
    ["xdg-open", url],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
  )

def _web_search(query: str) -> None:
  _open_url(CFG["search_url"].format(quote_plus(query)))

def _looks_like_url(s: str) -> bool:
  s = s.strip()
  if not s or " " in s:
    return False

  if s.startswith(("http://", "https://", "file://")):
    return True

  return bool(re.match(r"^[\w.-]+\.[a-z]{2,}(/.*)?$", s, re.IGNORECASE))


# ----------- Widgets ----------------------------------------------------------
class AppTile(Gtk.Button):
  """
    A single app grid entry that launches an app on click
  """

  def __init__(self, app_info: GioUnix.DesktopAppInfo, drawer: "Drawer"):
    super().__init__()
    self.app_info = app_info
    self.drawer = drawer
    self.add_css_class("app-tile")
    self.set_has_frame(False)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.set_halign(Gtk.Align.CENTER)

    icon = Gtk.Image()
    gicon = app_info.get_icon()
    if gicon:
      icon.set_from_gicon(gicon)

    else:
      icon.set_from_icon_name("application-x-executable")

    icon.set_pixel_size(CFG["icon_size"])
    box.append(icon)

    label = Gtk.Label(label=app_info.get_display_name() or "?")
    label.set_max_width_chars(14)
    label.set_ellipsize(3)
    label.set_justify(Gtk.Justification.CENTER)
    label.set_wrap(True)
    label.set_lines(2)
    box.append(label)

    self.set_child(box)
    self.connect("clicked", lambda _b: _launch_app_and_exit(app_info, drawer))

    # Right-click menu
    right_click = Gtk.GestureClick()
    right_click.set_button(Gdk.BUTTON_SECONDARY)
    right_click.connect("pressed", self._on_right_click)
    self.add_controller(right_click)

  def _on_right_click(self, _gesture, _n_press, _x, _y):
    """
      XXX:  Direct toggle (no menu) because popovers don't route input correctly
            through gtk4-layer-shell on this stack, so we skip the confirmation
            step.
    """
    self.drawer.fav_row.toggle_app(self.app_info.get_id())

class FavoritesRow(Gtk.Box):
  """
    Self-contained favorites section: header + tile grid + the pinned-id list.
  """

  def __init__(self, drawer: "Drawer", apps_by_id: dict):
    super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=20)

    self._drawer = drawer
    self._all_apps_by_id = apps_by_id
    self._fav_apps_by_id : list[str] = [
      i for i in favorites.load_favorites() if i in apps_by_id
    ]

    self._fav_header = Gtk.Label(label="Favorites", xalign=0)
    self._fav_header.add_css_class("category-header")
    self.append(self._fav_header)

    self._fav_flow = Gtk.FlowBox()
    self._fav_flow.set_max_children_per_line(CFG["columns"])
    self._fav_flow.set_min_children_per_line(1)
    self._fav_flow.set_homogeneous(True)
    self._fav_flow.set_selection_mode(Gtk.SelectionMode.NONE)
    self._fav_flow.set_column_spacing(6)
    self._fav_flow.set_row_spacing(10)
    self.append(self._fav_flow)

    self.rebuild()

  def rebuild(self):
    """
      Clear and repopulate tiles from the current id list.
    """
    child = self._fav_flow.get_first_child()
    while child is not None:
      nxt = child.get_next_sibling()
      self._fav_flow.remove(child)
      child = nxt

    self.set_visible(bool(self._fav_apps_by_id))
    for app_id in self._fav_apps_by_id:
      if (ai := self._all_apps_by_id.get(app_id)):
        self._fav_flow.append(AppTile(ai, self._drawer))

  def toggle_app(self, app_id: str):
    """
      Pin/unpin an app, then persist and refresh.
    """
    if app_id in self._fav_apps_by_id:
      self._fav_apps_by_id.remove(app_id)

    else:
      self._fav_apps_by_id.append(app_id)

    favorites.save_favorites(self._fav_apps_by_id)
    self.rebuild()

  def hide_favorites(self, is_searching: bool):
    """
      Hide the whole row while a search is in progress.
    """
    self.set_visible(not is_searching and bool(self._fav_apps_by_id))


class Drawer(Gtk.ApplicationWindow):
  """
    The app grid + launcher that makes up the 'drawer'
  """

  def __init__(self, app: Gtk.Application):
    super().__init__(application=app, title=config.APP_NAME)

    # Overlay: * keep at top *
    #   this app presents as a full screen overlay
    self._setup_overlay()

    # Data:
    #   load in all the app data from the .desktop files
    self._categories: list[tuple[str, Gtk.Label, Gtk.FlowBox]] = []
    self._apps_by_category = dict(cache.load_apps())
    all_apps_by_id = {}
    for apps in self._apps_by_category.values():
      for a in apps:
        all_apps_by_id[a.id] = a

    # Component construction:
    #   - search bar
    #   - app grid
    #   - (optional) fall back bar
    self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    self._root.set_margin_top(24)
    self._root.set_margin_bottom(24)
    self._root.set_margin_start(28)
    self._root.set_margin_end(28)

    self._root.set_hexpand(True)
    self._root.set_vexpand(True)

    #   search bar is on top
    self.search = Gtk.SearchEntry()
    self.search.set_placeholder_text("Search apps, type a URL, or query the web…")
    self.search.connect("search-changed", self._on_search_changed)
    self.search.connect("activate", self._on_search_activate)
    self._root.append(self.search)

    #   app grid is in the middle
    #     - first favorites row
    #     - second all the apps we know about, by category
    grid_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
    self.fav_row = FavoritesRow(self, all_apps_by_id)
    grid_box.append(self.fav_row)
    self._setup_app_grid(grid_box)

    #   optional bottom row for info if we're not selecting an app
    self.web_row = Gtk.Button()
    self.web_row.add_css_class("web-fallback")
    self.web_row.set_visible(False)
    self.web_row.connect("clicked", self._on_web_clicked)
    self._root.append(self.web_row)

    #   finally make the app grid scrollable
    scroller = Gtk.ScrolledWindow()
    scroller.set_vexpand(True)
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_child(grid_box)
    self._root.append(scroller)

    # Fullscreen Surface / Backdrop:
    #   the panel sits inside a backdrop box we own, so clicks *around* the
    #   panel land on a widget we can use to dismiss.
    backdrop = Gtk.Box()
    backdrop.add_css_class("backdrop")   # CSS supplies the inset + optional dim
    backdrop.append(self._root)
    self.set_child(backdrop)

    # Action Handlers:
    #   - clicks on the backdrop
    #   - typing in the search bar
    click = Gtk.GestureClick()
    click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    click.connect("pressed", self._on_backdrop_clicked)
    self.add_controller(click)

    ck = Gtk.EventControllerKey()
    ck.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    ck.connect("key-pressed", self._on_key_pressed)
    self.add_controller(ck)


  # ----- component construction helpers -----
  def _setup_overlay(self):
    """
      setup the this app as a full screen overlay with a margin so it's
      centered with breathing room
    """
    LayerShell.init_for_window(self)
    LayerShell.set_namespace(self, config.APP_NAME)
    LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
    LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.EXCLUSIVE)

    LayerShell.set_anchor(self, LayerShell.Edge.TOP,    True)
    LayerShell.set_anchor(self, LayerShell.Edge.BOTTOM, True)
    LayerShell.set_anchor(self, LayerShell.Edge.LEFT,   True)
    LayerShell.set_anchor(self, LayerShell.Edge.RIGHT,  True)

    LayerShell.set_margin(self, LayerShell.Edge.TOP, 60)
    LayerShell.set_margin(self, LayerShell.Edge.BOTTOM, 60)
    LayerShell.set_margin(self, LayerShell.Edge.LEFT, 200)
    LayerShell.set_margin(self, LayerShell.Edge.RIGHT, 200)

  def _setup_app_grid(self, grid_box):
    """
      Populate grid_box with one labeled FlowBox per non-empty category.
    """
    for cat in config.CATEGORY_ORDER:
      apps = self._apps_by_category.get(cat, [])
      if not apps:
        continue

      header = Gtk.Label(label=cat, xalign=0)
      header.add_css_class("category-header")
      grid_box.append(header)

      flow = Gtk.FlowBox()
      flow.set_max_children_per_line(CFG["columns"])
      flow.set_min_children_per_line(1)
      flow.set_homogeneous(True)
      flow.set_selection_mode(Gtk.SelectionMode.NONE)
      flow.set_column_spacing(6)
      flow.set_row_spacing(10)
      for ai in apps:
        flow.append(AppTile(ai, self))

      grid_box.append(flow)
      self._categories.append((cat, header, flow))


  # ----- action handlers -----
  def _on_backdrop_clicked(self, _gesture, _n_press, x, y):
    # did the click land in the drawer area? do nothing
    target = self.pick(x, y, Gtk.PickFlags.DEFAULT) # pylint: disable=no-member
    while target is not None:
      if target is self._root:
        return
      target = target.get_parent()

    # if it's outside the drawer? close ourselves
    self.get_application().dismiss()

  def _on_key_pressed(self, _kc, keyval, _kc2, _state):
    if keyval == Gdk.KEY_Escape:
      self.get_application().dismiss()
      return True

    return False

  def _on_search_changed(self, entry: Gtk.SearchEntry):
    q = entry.get_text().strip().lower()

    # Hide favorites row when searching
    self.fav_row.hide_favorites(bool(q))

    if not q:
      for _, header, flow in self._categories:
        header.set_visible(True)
        flow.set_visible(True)
        flow.set_filter_func(None)

      self.web_row.set_visible(False)
      return

    any_visible = False
    for cat, header, flow in self._categories:
      apps = self._apps_by_category.get(cat, [])
      has_match = any(_matches(a, q) for a in apps)
      header.set_visible(has_match)
      flow.set_visible(has_match)

      if has_match:
        any_visible = True
        flow.set_filter_func(
          lambda child, qq=q: _matches(child.get_child().app_info, qq)
        )
        flow.invalidate_filter()

    if any_visible:
      self.web_row.set_visible(False)

    else:
      raw = entry.get_text().strip()
      if result := math.try_math(raw) is not None:
        self.web_row.set_label(f"  Math result is {result}")

      elif _looks_like_url(raw):
        self.web_row.set_label(f"  Open  {raw}")

      else:
        self.web_row.set_label(f"  Search the web for  \u201c{raw}\u201d")

      self.web_row.set_visible(True)

  def _on_search_activate(self, entry: Gtk.SearchEntry):
    """
      Handler for hitting enter in the search bar
    """
    raw = entry.get_text().strip()
    if not raw:
      return

    # we first check for an app match and launch it
    query = raw.lower()
    for cat, _h, _flow in self._categories:
      for app_info in self._apps_by_category.get(cat, []):
        if _matches(app_info, query):
          _launch_app_and_exit(app_info, self)
          return

    # then we check the other features
    self._handle_non_apps(raw)

  def _on_web_clicked(self, _btn):
    """
      Handler for clicking the button at the bottom of the results
    """
    raw = self.search.get_text().strip()
    if not raw:
      return

    # there's no button when we pick an app, so only have to handle the
    # other features on a button click
    self._handle_non_apps(raw)

  def _handle_non_apps(self, text):
    """
      handle the execution of non-app search features
    """
    if (result := math.try_math(text)) is not None:
      out = str(result)
      if shutil.which("wl-copy"):
        # copy the results to the clipboard for convenience
        subprocess.run(["wl-copy", "--", out], check=False)

      else:
        # fallback: best-effort, may not survive focus loss on layer-shell
        Gdk.Display.get_default().get_clipboard().set(out)

      self.web_row.set_label("  Math result is copied to clipboard!")

    elif _looks_like_url(text):
      _open_url(text)

    else:
      _web_search(text)

    self.get_application().dismiss()
