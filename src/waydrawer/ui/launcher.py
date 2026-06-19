# ----------- ui Launcher View -------------------------------------------------
"""
  The primary view of this app, the Launcher View represents the app grid and
  launcher bar used to interact with waydrawer.
"""
from __future__ import annotations

import json
import re
import os
import shutil
import sys
import subprocess
from urllib.parse import quote_plus

# pylint: disable=wrong-import-position
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("GioUnix", "2.0")
from gi.repository import Gdk, GioUnix, Gio, GLib, GObject, Gtk

from waydrawer import cache
from waydrawer import config
from waydrawer import favorites
from waydrawer import try_math
from waydrawer import shortcuts

# ----------- Launcher (app grid + search bar) ---------------------------------
class LauncherView(Gtk.Box):
  """
    Full-surface launcher page: the search bar + app grid + clickable action
    bar. Owns the app and shortcut data it displays, and keeps itself current
    with on-disk state via reload().
  """
  # pylint: disable=too-many-instance-attributes

  def __init__(self, drawer):
    super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)

    self._drawer = drawer

    # Data:
    #   load in all the app data from the .desktop files
    self._categories: list[tuple[str, Gtk.Label, Gtk.FlowBox]] = []
    self._running: set[str] = set()
    self._apps_by_category, all_apps_by_id = self._load_apps()

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
    self._app_grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)

    self.fav_row = FavoritesRow(self, all_apps_by_id)
    self._app_grid.append(self.fav_row)

    self._setup_app_grid(self._apps_by_category)

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
    self._scroller.set_child(self._app_grid)
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
      Make this view current with on-disk state: app list, config, shortcuts .
      The grid is only rebuilt when the app set changed; otherwise we just push
      any config change onto the existing tiles.
    """
    by_category, all_apps_by_id = self._load_apps()
    cfg_changed = config.reload()

    if by_category != self._apps_by_category:
      # update only if we've got a diff between the old and new sets of apps
      self._apps_by_category = by_category
      self._setup_app_grid(by_category)
      self.fav_row.refresh(all_apps_by_id)

    elif cfg_changed:
      self.apply_config()

    # always try shortcuts. they only load themselves if they've been updated
    self._shortcuts = shortcuts.load()

    # flag apps that already have a window open
    self.refresh_running()

  def reset(self):
    """
      fresh search and scroll position for a brand new show
    """
    self.search.set_text("")
    vadj = self._scroller.get_vadjustment()
    vadj.set_value(vadj.get_lower())

  def focus_search(self):
    """
      make sure the user input has focus
    """
    self.search.grab_focus()

  def launch_app_and_hide(self, ai):
    """
      Launch the app represented by the given app info. Gio handles the
      .desktop fine print for us.
    """
    info = Gio.DesktopAppInfo.new_from_filename(ai.filename)
    if info is None:
      print(f"[waydrawer] cannot load {ai.get_id()}", file=sys.stderr)
      return

    def finish(src, res):
      try:
        src.launch_uris_finish(res)

      except GLib.Error as e:
        print(f"[waydrawer] launch failed: {e}", file=sys.stderr)

    info.launch_uris_async([], _launch_ctx(), None, _held(finish))
    self._drawer.dismiss()

  def launch_shortcut_and_hide(self, target: str):
    """
      Opens target with the user's registered default handler. Falls back to
      xdg-open if the launch fails.
    """
    uri = Gio.File.new_for_commandline_arg(target).get_uri()

    def finish(_src, res):
      try:
        Gio.AppInfo.launch_default_for_uri_finish(res)

      except GLib.Error:
        _spawn_detached(["xdg-open", target])

    Gio.AppInfo.launch_default_for_uri_async(uri, _launch_ctx(), None, _held(finish))
    self._drawer.dismiss()

  def refresh_running(self):
    """
      Flag apps with an open window. Called on each show; cheap snapshot via
      hyprctl, no live subscription.
    """
    self._running = _running_classes()
    self.fav_row.mark_running(self._running)
    for _cat, _h, flow in self._categories:
      _mark_flow_running(flow, self._running)

  def running_set(self) -> set[str]:
    """
      Window classes flagged running as of the last refresh_running().
    """
    return self._running

  # ----- component construction helpers -----
  def _load_apps(self):
    """
      Read the app cache and return (categories, apps_by_id). Pure: the caller
      owns assignment to self, so ordering is visible at the call site.
    """
    by_category = dict(cache.load_apps())
    by_id = {a.id: a for apps in by_category.values() for a in apps}
    return by_category, by_id

  def _setup_app_grid(self, by_category):
    """
      (Re)build one labeled FlowBox per non-empty category into self._app_grid.
      Idempotent; reads only its argument, not self state.
    """
    for _cat, header, flow in self._categories:
      self._app_grid.remove(header)
      self._app_grid.remove(flow)
    self._categories.clear()

    for cat in config.CATEGORY_ORDER:
      apps = by_category.get(cat, [])
      if not apps:
        continue

      header = Gtk.Label(label=cat, xalign=0)
      header.add_css_class("category-header")
      self._app_grid.append(header)

      flow = Gtk.FlowBox()
      flow.set_max_children_per_line(config.CFG["columns"])
      flow.set_min_children_per_line(1)
      flow.set_homogeneous(True)
      flow.set_selection_mode(Gtk.SelectionMode.NONE)
      flow.set_column_spacing(6)
      flow.set_row_spacing(10)

      for ai in apps:
        flow.append(AppTile(ai, self))

      self._app_grid.append(flow)
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

    # refilter the grid first so it's correct regardless of the suggestion below
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

    # the bar must advertise exactly what Enter does, or it lies. Enter's order:
    # exact shortcut -> first app -> _handle_non_apps (prefix sc / math / url / web)
    raw = entry.get_text().strip()

    # 1. exact shortcut wins outright, ahead of any app match
    if (sc := shortcuts.match(self._shortcuts, raw, exact=True)):
      self.web_row.set_label(f"  Open Shortcut '{sc[0]}'")
      self.web_row.set_visible(True)
      return

    # 2. apps matched -> Enter launches the first tile; no bar suggestion
    if any_visible:
      self.web_row.set_visible(False)
      return

    # 3. no apps -> same fallback chain _handle_non_apps uses
    if (sc := shortcuts.match(self._shortcuts, raw, exact=False)):
      self.web_row.set_label(f"  Open Shortcut '{sc[0]}'")

    elif (result := try_math.process(raw)) is not None:
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

    # an exact shortcut name runs immediately, ahead of any app match
    if (sc := shortcuts.match(self._shortcuts, raw, exact=True)):
      self.launch_shortcut_and_hide(sc[1])
      return

    # we first check for an app match and launch it
    query = raw.lower()
    for cat, _h, _flow in self._categories:
      for app_info in self._apps_by_category.get(cat, []):
        if _matches(app_info, query):
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

    if (result := try_math.process(text)) is not None:
      out = str(result)
      if shutil.which("wl-copy"):
        # copy the results to the clipboard for convenience
        subprocess.run(["wl-copy", "--", out], check=False, env=_child_env())

      else:
        # fallback: best-effort, may not survive focus loss on layer-shell
        Gdk.Display.get_default().get_clipboard().set(out)

    elif _looks_like_url(text):
      _open_url(text)

    else:
      # remove the placeholder {}, escape the input, and open the url
      _open_url(config.CFG["search_url"].replace("{}", quote_plus(text)))

    self._drawer.dismiss()


# ----------- Rows (app grid sections) ------------------------------------------
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
    self._fav_flow.set_max_children_per_line(config.CFG["columns"])
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
        tile = AppTile(ai, self._launcher)
        self._wire_reorder(tile, app_id)
        self._fav_flow.append(tile)

    self.mark_running(self._launcher.running_set())   # keep dots across rebuilds

  def refresh(self, apps_by_id: dict):
    """
      App set changed on disk: adopt the new map, drop favorites whose app is
      gone, and rebuild.
    """
    self._all_apps_by_id = apps_by_id
    self._fav_apps_by_id = [i for i in self._fav_apps_by_id if i in apps_by_id]
    self.rebuild()

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

  def mark_running(self, running: set[str]):
    """
      Push running state onto favorite tiles.
    """
    _mark_flow_running(self._fav_flow, running)

  # ---- internal helpers ----
  def _wire_reorder(self, tile, app_id: str):
    """
      Make a favorite tile draggable onto its siblings to reorder. Only
      favorites are wired; category tiles stay inert. Primary-button drag only,
      so the right-click pin/unpin gesture is untouched.
    """
    drag = Gtk.DragSource()
    drag.set_actions(Gdk.DragAction.MOVE)
    drag.connect(
      "prepare",
      lambda _s, _x, _y, aid=app_id: Gdk.ContentProvider.new_for_value(aid)
    )
    drag.connect(
      "drag-begin",
      lambda s, _d, t=tile: s.set_icon(Gtk.WidgetPaintable.new(t), 0, 0)
    )
    tile.add_controller(drag)

    drop = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
    drop.connect(
      "drop",
      lambda _t, src_id, _x, _y, dst=app_id: self._reorder(src_id, dst)
    )
    tile.add_controller(drop)

  def _reorder(self, src_id: str, dst_id: str) -> bool:
    """
      Move src_id into dst_id's slot, persist, rebuild. Returns True if the
      order changed (the drop's accepted/rejected result).
    """
    if src_id == dst_id or src_id not in self._fav_apps_by_id:
      return False

    self._fav_apps_by_id.remove(src_id)
    dst = (self._fav_apps_by_id.index(dst_id)
           if dst_id in self._fav_apps_by_id else len(self._fav_apps_by_id))
    self._fav_apps_by_id.insert(dst, src_id)

    favorites.save(self._fav_apps_by_id)
    self.rebuild()
    return True

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

    # add the app's icon
    self._icon = Gtk.Image()
    if gicon := app_info.get_icon():
      self._icon.set_from_gicon(gicon)

    else:
      self._icon.set_from_icon_name("application-x-executable")

    box.append(self._icon)

    # add the text name
    label = Gtk.Label(label=app_info.get_display_name() or "?")
    label.set_max_width_chars(14)
    label.set_ellipsize(3) # PANGO_ELLIPSIZE_END
    label.set_justify(Gtk.Justification.CENTER)
    label.set_wrap(True)
    label.set_lines(2)
    box.append(label)

    # add a dot to indicate a running app
    self._dot = Gtk.Box()
    self._dot.add_css_class("running-dot")
    self._dot.set_halign(Gtk.Align.CENTER)
    self._dot.set_opacity(0.0)   # reserve space; opacity toggle avoids reflow
    box.append(self._dot)

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
    self._icon.set_pixel_size(config.CFG["icon_size"])

  def set_running(self, is_running: bool):
    """
      Toggle the running-window indicator.
    """
    self._dot.set_opacity(1.0 if is_running else 0.0)

  def _on_right_click(self, _gesture, _n_press, _x, _y):
    """
      XXX:  Direct toggle (no menu) because popovers don't route input correctly
            through gtk4-layer-shell on this stack, so we skip the confirmation
            step.
    """
    self.launcher.fav_row.toggle_app(self.app_info.get_id())


# ----------- Internal Helpers ------------------------------------------------
def _apply_flow_config(flow):
  """
    push current CFG onto a tile FlowBox and its children
  """
  flow.set_max_children_per_line(config.CFG["columns"])
  child = flow.get_first_child()
  while child is not None:
    child.get_child().apply_config()
    child = child.get_next_sibling()

# --- string checks ---
def _matches(app_info: GioUnix.DesktopAppInfo, q: str) -> bool:
  """
    Given some app info and a query, return true if they match.
  """
  if not q:
    return True

  name = (app_info.get_display_name() or "").lower()
  generic = (app_info.get_generic_name() or "").lower()
  keywords = " ".join(app_info.get_keywords() or []).lower()
  return q in name or q in generic or q in keywords

def _looks_like_url(s: str) -> bool:
  """
    Return true if the given string looks like a URL
  """
  s = s.strip()
  if not s or " " in s:
    return False

  if s.startswith(("http://", "https://", "file://")):
    return True

  return bool(re.match(r"^[\w.-]+\.[a-z]{2,}(/.*)?$", s, re.IGNORECASE))

# --- app lauching ---
def _open_url(url: str) -> None:
  """
    Given a url, open it in the default browser
  """
  if not url.startswith(("http://", "https://", "file://")):
    url = "https://" + url

  _spawn_detached(["xdg-open", url])

def _held(finish):
  """
    Wrap an async-finish callback so the application is held alive until the
    launch completes. Async launches go over a GLib/D-Bus round trip and in
    non-daemon mode we may exit before it ends -- the hold keeps the process
    alive until the callback fires.

    Caller contract:  only invoke _held once the async op is guaranteed to
                      start, since the release lives in the returned callback.
  """
  app = Gio.Application.get_default()
  if app:
    app.hold()

  def done(src, res):
    try:
      finish(src, res)

    finally:
      if app:
        app.release()

  return done

def _launch_ctx() -> Gio.AppLaunchContext:
  """
    Launch context for child apps. Prefer the Gdk one (carries an
    xdg-activation focus token on Wayland). Fall back to plain Gio if no
    display. Either way, scrub the re-exec env injection (see _child_env).
  """
  display = Gdk.Display.get_default()
  ctx = display.get_app_launch_context() if display else Gio.AppLaunchContext()
  env = _child_env()

  for var in ("LD_PRELOAD", "PYTHONPATH"):
    ctx.unsetenv(f"_WAYDRAWER_ORIG_{var}") # undo our temp saves for the kids
    if var in env:
      ctx.setenv(var, env[var])

    else:
      ctx.unsetenv(var)

  return ctx

def _spawn_detached(argv: list[str]) -> None:
  """
    Launch the given process defined by argv as a totall disconnected process
    from waydrawer so their futures aren't intertwined.
  """
  subprocess.Popen(   # pylint: disable=consider-using-with
    argv,
    env=_child_env(),
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
    close_fds=True,
  )

def _child_env() -> dict[str, str]:
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

# --- running-app detection ---
def _running_classes() -> set[str]:
  """
    Lowercased window classes currently open under Hyprland (class +
    initialClass). Empty set on any failure -> no indicators, never a crash.
  """
  try:
    out = subprocess.run(
      ["hyprctl", "clients", "-j"],
      capture_output=True, text=True, env=_child_env(),
      timeout=1.0, check=True,
    ).stdout
    clients = json.loads(out)

  except (OSError, subprocess.SubprocessError, ValueError):
    return set()

  classes = set()
  for c in clients:
    for key in ("class", "initialClass"):
      if v := (c.get(key) or "").lower():
        classes.add(v)

  return classes

def _is_running(ai, running: set[str]) -> bool:
  """
    True if this app has an open window. Prefer StartupWMClass; fall back to the
    desktop-id stem and its last reverse-DNS component (firefox.desktop ->
    firefox; org.mozilla.firefox -> firefox).
  """
  if not running:
    return False

  if (wm := ai.get_startup_wm_class().lower()) and wm in running:
    return True

  stem = ai.get_id().removesuffix(".desktop").lower()
  return stem in running or stem.rsplit(".", 1)[-1] in running

def _mark_flow_running(flow, running):
  """
    Push running state onto every tile in a FlowBox.
  """
  child = flow.get_first_child()
  while child is not None:
    child.get_child().set_running(_is_running(child.get_child().app_info, running))
    child = child.get_next_sibling()
