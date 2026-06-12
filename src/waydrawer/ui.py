# ----------- User Interface for waydrawer -------------------------------------
"""
  Using Gtk, we build the needed widgets and helpers to define the UI. The
  handling of styling from the config files is done in style.py and applied in
  main()
"""
from __future__ import annotations

import shutil
import subprocess

# pylint: disable=wrong-import-position
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("GioUnix", "2.0")
from gi.repository import GioUnix, Gtk, Gdk, Gtk4LayerShell as LayerShell

from waydrawer import cache
from waydrawer import config
from waydrawer import favorites
from waydrawer import math
from waydrawer import shortcuts
from waydrawer import util


def _apply_flow_config(flow):
  """ 
    push current CFG onto a tile FlowBox and its children
  """
  flow.set_max_children_per_line(util.CFG["columns"])
  child = flow.get_first_child()
  while child is not None:
    child.get_child().apply_config()
    child = child.get_next_sibling()


# ----------- Tiles (grid entries) --------------------------------------------
class AppTile(Gtk.Button):
  """
    A single app grid entry that launches an app on click
  """

  def __init__(self, app_info: GioUnix.DesktopAppInfo, launcher: "LauncherView"):
    super().__init__()
    self.app_info = app_info
    self.launcher = launcher
    self.add_css_class("app-tile")
    self.set_has_frame(False)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.set_halign(Gtk.Align.CENTER)

    self._icon = Gtk.Image()
    if gicon := app_info.get_icon():
      self._icon.set_from_gicon(gicon)

    else:
      self._icon.set_from_icon_name("application-x-executable")

    box.append(self._icon)

    label = Gtk.Label(label=app_info.get_display_name() or "?")
    label.set_max_width_chars(14)
    label.set_ellipsize(3)
    label.set_justify(Gtk.Justification.CENTER)
    label.set_wrap(True)
    label.set_lines(2)
    box.append(label)

    self.set_child(box)
    self.connect("clicked", lambda _b: launcher.launch_app_and_hide(app_info))

    # Right-click menu
    right_click = Gtk.GestureClick()
    right_click.set_button(Gdk.BUTTON_SECONDARY)
    right_click.connect("pressed", self._on_right_click)
    self.add_controller(right_click)

    # apply the relevant user config settings
    self.apply_config()

  def apply_config(self):
    """ 
      re-apply config values baked in at construction
    """
    self._icon.set_pixel_size(util.CFG["icon_size"])

  def _on_right_click(self, _gesture, _n_press, _x, _y):
    """
      XXX:  Direct toggle (no menu) because popovers don't route input correctly
            through gtk4-layer-shell on this stack, so we skip the confirmation
            step.
    """
    self.launcher.fav_row.toggle_app(self.app_info.get_id())


# ----------- Rows (drawer sections) ------------------------------------------
class FavoritesRow(Gtk.Box):
  """
    Self-contained favorites section: header + tile grid + the pinned-id list.
  """

  def __init__(self, launcher: "LauncherView", apps_by_id: dict):
    super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=20)

    self._launcher = launcher
    self._all_apps_by_id = apps_by_id
    self._fav_apps_by_id : list[str] = [
      i for i in favorites.load() if i in apps_by_id
    ]

    self._fav_header = Gtk.Label(label="Favorites", xalign=0)
    self._fav_header.add_css_class("category-header")
    self.append(self._fav_header)

    self._fav_flow = Gtk.FlowBox()
    self._fav_flow.set_max_children_per_line(util.CFG["columns"])
    self._fav_flow.set_min_children_per_line(1)
    self._fav_flow.set_homogeneous(True)
    self._fav_flow.set_selection_mode(Gtk.SelectionMode.NONE)
    self._fav_flow.set_column_spacing(6)
    self._fav_flow.set_row_spacing(10)
    self.append(self._fav_flow)

    self.rebuild()

  def apply_config(self):
    """
      apply the values from the user config files
    """
    _apply_flow_config(self._fav_flow)

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
        self._fav_flow.append(AppTile(ai, self._launcher))

  def toggle_app(self, app_id: str):
    """
      Pin/unpin an app, then persist and refresh.
    """
    if app_id in self._fav_apps_by_id:
      self._fav_apps_by_id.remove(app_id)

    else:
      self._fav_apps_by_id.append(app_id)

    favorites.save(self._fav_apps_by_id)
    self.rebuild()

  def hide_favorites(self, is_searching: bool):
    """
      Hide the whole row while a search is in progress.
    """
    self.set_visible(not is_searching and bool(self._fav_apps_by_id))


# ----------- Launcher view ----------------------------------------------------
# pylint: disable=too-many-instance-attributes
class LauncherView(Gtk.Box):
  """
    Full-surface launcher page: the search bar + app grid + clickable action
    bar. Owns the app and shortcut data it displays, and keeps itself current
    with on-disk state via reload().
  """

  def __init__(self, drawer: "Drawer"):
    super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)

    self._drawer = drawer

    # Data:
    #   load in all the app data from the .desktop files
    self._categories: list[tuple[str, Gtk.Label, Gtk.FlowBox]] = []
    self._apps_by_category = dict(cache.load_apps())
    all_apps_by_id = {}
    for apps in self._apps_by_category.values():
      for a in apps:
        all_apps_by_id[a.id] = a

    #   read all the user shortcuts from disk
    self._shortcuts = shortcuts.load()

    #   search bar + settings gear share the top row.
    self.search = Gtk.SearchEntry()
    self.search.set_placeholder_text("Search apps, type a URL, or query the web…")
    self.search.set_hexpand(True)
    self.search.connect("search-changed", self._on_search_changed)
    self.search.connect("activate", self._on_search_activate)

    gear = Gtk.Button()
    gear.set_icon_name("preferences-system-symbolic")
    gear.set_has_frame(False)
    gear.add_css_class("settings-gear")
    gear.connect("clicked", lambda _b: self._drawer.show_settings())

    search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    search_row.append(self.search)
    search_row.append(gear)
    self.append(search_row)

    #   app grid in the middle: favorites row, then apps by category
    app_grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)

    self.fav_row = FavoritesRow(self, all_apps_by_id)
    app_grid.append(self.fav_row)

    self._setup_app_grid(app_grid)

    #   optional bottom row for info if we're not selecting an app
    self.web_row = Gtk.Button()
    self.web_row.add_css_class("web-fallback")
    self.web_row.set_visible(False)
    self.web_row.connect("clicked", self._on_web_clicked)
    self.append(self.web_row)

    #   make the app grid scrollable & add it to the launcher view
    self._scroller = Gtk.ScrolledWindow()
    self._scroller.set_vexpand(True)
    self._scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    self._scroller.set_child(app_grid)
    self.append(self._scroller)

  def apply_config(self):
    """
      apply current user config values in CFG onto live widgets
    """
    self.fav_row.apply_config()
    for _cat, _header, flow in self._categories:
      _apply_flow_config(flow)

  def reload(self):
    """
      make this view current with on-disk state
    """
    # reload the shortcuts and config variables if they've changed
    self._shortcuts = shortcuts.load()
    if config.reload():
      self.apply_config()

  def reset(self):
    """
      fresh search and scroll position for a brand new show
    """
    self.search.set_text("")

    # reset the scroll position of the window back to the start
    vadj = self._scroller.get_vadjustment()
    vadj.set_value(vadj.get_lower())

  def focus_search(self):
    """
      make sure the user input has focus
    """
    self.search.grab_focus()

  def launch_app_and_hide(self, app_info: GioUnix.DesktopAppInfo):
    """
      hide the app after launching an external process
    """
    util.launch_app(app_info)
    self._drawer.get_application().dismiss()

  def launch_shortcut_and_hide(self, target: str):
    """
      hide the app after launching a user defined shortcut
    """
    util.launch_default_app(target)
    self._drawer.get_application().dismiss()

  # ----- component construction helpers -----
  def _setup_app_grid(self, app_grid):
    """
      Populate app_grid with one labeled FlowBox per non-empty category.
    """
    for cat in config.CATEGORY_ORDER:
      apps = self._apps_by_category.get(cat, [])
      if not apps:
        continue

      header = Gtk.Label(label=cat, xalign=0)
      header.add_css_class("category-header")
      app_grid.append(header)

      flow = Gtk.FlowBox()
      flow.set_max_children_per_line(util.CFG["columns"])
      flow.set_min_children_per_line(1)
      flow.set_homogeneous(True)
      flow.set_selection_mode(Gtk.SelectionMode.NONE)
      flow.set_column_spacing(6)
      flow.set_row_spacing(10)
      for ai in apps:
        flow.append(AppTile(ai, self))

      app_grid.append(flow)
      self._categories.append((cat, header, flow))


  # ----- action handlers -----
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
      has_match = any(util.matches(a, q) for a in apps)
      header.set_visible(has_match)
      flow.set_visible(has_match)

      if has_match:
        any_visible = True
        flow.set_filter_func(
          lambda child, qq=q: util.matches(child.get_child().app_info, qq)
        )
        flow.invalidate_filter()

    # a matching shortcut owns the suggestion bar (this is the typeahead)
    raw = entry.get_text().strip()
    if (sc := shortcuts.match(self._shortcuts, raw, exact=False)):
      self.web_row.set_label(f"  Open  {sc[0]}")
      self.web_row.set_visible(True)
      return

    if any_visible:
      self.web_row.set_visible(False)

    else:
      if (result := math.try_math(raw)) is not None:
        self.web_row.set_label(f"  Math result is {result}")

      elif util.looks_like_url(raw):
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

    # an exact shortcut name runs immediately, ahead of any app match
    if (sc := shortcuts.match(self._shortcuts, raw, exact=True)):
      self.launch_shortcut_and_hide(sc[1])
      return

    # we first check for an app match and launch it
    query = raw.lower()
    for cat, _h, _flow in self._categories:
      for app_info in self._apps_by_category.get(cat, []):
        if util.matches(app_info, query):
          self.launch_app_and_hide(app_info)
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
    if (sc := shortcuts.match(self._shortcuts, text, exact=False)):
      self.launch_shortcut_and_hide(sc[1])
      return

    if (result := math.try_math(text)) is not None:
      out = str(result)
      if shutil.which("wl-copy"):
        # copy the results to the clipboard for convenience
        subprocess.run(["wl-copy", "--", out], check=False)

      else:
        # fallback: best-effort, may not survive focus loss on layer-shell
        Gdk.Display.get_default().get_clipboard().set(out)

      self.web_row.set_label("  Math result is copied to clipboard!")

    elif util.looks_like_url(text):
      util.open_url(text)

    else:
      util.web_search(text)

    self._drawer.get_application().dismiss()


# ----------- Settings view ---------------------------------------------------
class SettingsView(Gtk.Box):
  """
    Full-surface settings page swapped in for the launcher. Edits to config
    values and shortcuts are written straight through to disk as they happen.
  """

  def __init__(self, drawer: "Drawer"):
    super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    self._drawer = drawer
    self.add_css_class("settings")

    # header: back to launcher + title
    header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    back = Gtk.Button()
    back.set_icon_name("go-previous-symbolic")
    back.set_has_frame(False)
    back.add_css_class("settings-back")
    back.connect("clicked", lambda _b: self._drawer.show_launcher())
    title = Gtk.Label(label="Settings", xalign=0)
    title.set_hexpand(True)
    title.add_css_class("category-header")
    header.append(back)
    header.append(title)
    self.append(header)

    # scrollable body
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    body.append(self._build_config_section())
    body.append(self._build_shortcuts_section())

    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.set_vexpand(True)
    scroller.set_child(body)
    self.append(scroller)

  def reload_shortcuts(self):
    """
      Rebuild the shortcut grid from disk, then re-attach the add row at the
      bottom so it shares the same three columns.
    """
    child = self._sc_grid.get_first_child()
    while child is not None:
      nxt = child.get_next_sibling()
      self._sc_grid.remove(child)
      child = nxt

    row = 0
    for name, target in shortcuts.load().items():
      name_lbl = Gtk.Label(label=name, xalign=0)

      target_entry = Gtk.Entry()
      target_entry.set_text(target)
      target_entry.set_hexpand(True)
      target_entry.connect(
        "activate",
        lambda e, n=name: shortcuts.save(n, e.get_text())
      )

      focus = Gtk.EventControllerFocus()
      focus.connect(
        "leave",
        lambda _c, e=target_entry, n=name: shortcuts.save(n, e.get_text())
      )
      target_entry.add_controller(focus)

      del_btn = Gtk.Button()
      del_btn.set_icon_name("user-trash-symbolic")
      del_btn.set_halign(Gtk.Align.END)
      del_btn.connect("clicked", lambda _b, n=name: self._on_delete_shortcut(n))

      self._sc_grid.attach(name_lbl, 0, row, 1, 1)
      self._sc_grid.attach(target_entry, 1, row, 1, 1)
      self._sc_grid.attach(del_btn, 2, row, 1, 1)
      row += 1

    # add row last, same three columns
    self._sc_grid.attach(self._sc_name, 0, row, 1, 1)
    self._sc_grid.attach(self._sc_target, 1, row, 1, 1)
    self._sc_grid.attach(self._add_btn, 2, row, 1, 1)

  def reload_config(self):
    """
      Rebuild the config rows from current CFG values. Fresh widgets each
      entry, so connect-after-seed keeps the rebuild from firing saves.
    """
    child = self._cfg_grid.get_first_child()
    while child is not None:
      nxt = child.get_next_sibling()
      self._cfg_grid.remove(child)
      child = nxt

    for row, key in enumerate(sorted(config.CFG_DEFAULTS)):
      lbl = Gtk.Label(label=key, xalign=0)
      lbl.set_hexpand(False)
      self._cfg_grid.attach(lbl, 0, row, 1, 1)
      self._cfg_grid.attach(self._config_widget(key), 1, row, 1, 1)

  # ----- config section -----
  def _build_config_section(self):
    """
      One row per known config key; widget picked from the value's type.
    """
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

    header = Gtk.Label(label="Config", xalign=0)
    header.add_css_class("category-header")
    box.append(header)

    self._cfg_grid = Gtk.Grid(column_spacing=12, row_spacing=8)
    self.reload_config()

    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    body.set_margin_start(32)
    body.append(self._cfg_grid)
    box.append(body)

    return box

  def _config_widget(self, key):
    """
      bool -> Switch, int -> SpinButton, else -> Entry. bool is tested before
      int because bool is an int subclass. Signals are connected after the
      initial set so seeding the widget doesn't trigger a spurious save.
    """
    val = config.CFG[key]

    if isinstance(val, bool):
      sw = Gtk.Switch()
      sw.set_active(val)
      sw.set_halign(Gtk.Align.START)
      sw.connect("state-set", lambda _s, state, k=key: config.save(k, state))
      return sw

    if isinstance(val, int):
      spin = Gtk.SpinButton.new_with_range(1, 512, 1)
      spin.set_value(val)
      spin.set_halign(Gtk.Align.START)
      spin.connect(
        "value-changed",
        lambda s, k=key: config.save(k, int(s.get_value()))
      )
      return spin

    entry = Gtk.Entry()
    entry.set_text(str(val))
    entry.set_hexpand(True)
    entry.connect("activate", lambda e, k=key: config.save(k, e.get_text()))
    focus = Gtk.EventControllerFocus()
    focus.connect(
      "leave",
      lambda _c, e=entry, k=key: config.save(k, e.get_text())
    )
    entry.add_controller(focus)
    return entry

  # ----- shortcuts section -----
  def _build_shortcuts_section(self):
    """
      Existing shortcuts plus an add row at the bottom. All rows share one
      Gtk.Grid so the name / target / button columns line up.
    """
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

    header = Gtk.Label(label="Shortcuts", xalign=0)
    header.add_css_class("category-header")
    box.append(header)

    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    body.set_margin_start(32)

    self._sc_grid = Gtk.Grid(column_spacing=6, row_spacing=6)
    body.append(self._sc_grid)

    box.append(body)

    # add-row widgets persist across reloads and are re-attached as the last
    # grid row each rebuild.
    self._sc_name = Gtk.Entry()
    self._sc_name.set_placeholder_text("name")
    self._sc_name.set_width_chars(14)   # font-relative; sets the name column width
    self._sc_name.set_alignment(0.5)

    self._sc_target = Gtk.Entry()
    self._sc_target.set_placeholder_text("target for xdg-open")
    self._sc_target.set_hexpand(True)

    self._add_btn = Gtk.Button(label="Add")
    self._add_btn.set_halign(Gtk.Align.END)
    self._add_btn.connect("clicked", self._on_add_shortcut)

    # call the common reload to set the rows
    self.reload_shortcuts()
    return box

  def _on_add_shortcut(self, _btn):
    name = self._sc_name.get_text().strip()
    target = self._sc_target.get_text().strip()
    if not name or not target:
      return

    shortcuts.save(name, target)
    self._sc_name.set_text("")
    self._sc_target.set_text("")
    self.reload_shortcuts()

  def _on_delete_shortcut(self, name):
    shortcuts.delete(name)
    self.reload_shortcuts()


# ----------- Drawer (main app window) ----------------------------------------
class Drawer(Gtk.ApplicationWindow):
  """
    The full screen surface holding the launcher and settings views. Routes
    between them and handles dismissal; the views own their own content.
  """

  def __init__(self, app: Gtk.Application):
    super().__init__(application=app, title=config.APP_NAME)

    # Overlay: * keep at top *
    #   this app presents as a full screen overlay
    self._setup_overlay()

    # Panel Construction:
    #   _root is the persistent panel chrome (margins + styling). Its content
    #   is a stack that swaps the launcher for the settings view -- a full
    #   swap, so the search row is part of the launcher and gone while in
    #   settings. Both pages bubble clicks up to _root, so the backdrop
    #   pick-walk below is unchanged.
    self._root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    self._root.set_margin_top(24)
    self._root.set_margin_bottom(24)
    self._root.set_margin_start(28)
    self._root.set_margin_end(28)

    self._root.set_hexpand(True)
    self._root.set_vexpand(True)

    # stack of views
    self._stack = Gtk.Stack()
    self._stack.set_vexpand(True)
    self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
    self._stack.set_transition_duration(120)
    self._root.append(self._stack)

    #   launcher View
    self._launcher_view = LauncherView(self)
    self._stack.add_named(self._launcher_view, "launcher")

    #   settings View
    self._settings_view = SettingsView(self)
    self._stack.add_named(self._settings_view, "settings")

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

    # focus search the moment the surface maps, before any keystroke can land.
    # idle_add (used in show/reset_for_show) runs below input priority, so a
    # fast first keystroke beats it; "map" fires synchronously as we present.
    self.connect("map", lambda _w: self._launcher_view.focus_search())

  def reset_for_show(self):
    """
      reset the various bits of ui and state when this window is shown,
      typically from the daemon
    """
    self.show_launcher()
    self._launcher_view.reset()

  def show_settings(self):
    """
      swap the panel to the settings view, current with on-disk state
    """
    config.reload()
    self._settings_view.reload_config()
    self._settings_view.reload_shortcuts()
    self._stack.set_visible_child_name("settings")

  def show_launcher(self):
    """
      swap the panel to the launcher, load on-disk state, and refocus the
      search entry
    """
    self._launcher_view.reload()
    self._stack.set_visible_child_name("launcher")
    self._launcher_view.focus_search()

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
    if ret := keyval == Gdk.KEY_Escape:
      if self._stack.get_visible_child_name() == "settings":
        # escape backs out of settings first
        self.show_launcher()

      else:
        # then dismisses the drawer
        self.get_application().dismiss()

    return ret
