# ----------- ui Drawer (main app window) --------------------------------------
"""
  Drawer is the main app window for waydrawer. It primarily manages the various
  views that can be stacked into the layer shell that we use for this app.
"""
from __future__ import annotations

# pylint: disable=wrong-import-position
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, Gdk, Gtk4LayerShell as LayerShell

from waydrawer import config
from waydrawer.ui.settings import SettingsView
from waydrawer.ui.launcher import LauncherView

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
    self.show_launcher()            # refreshes CFG via launcher.reload()
    self._apply_overlay_margins()   # pick up a margin change without a restart
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

  def dismiss(self):
    """
      Keep all the calls to dismissing the ui from various views in one place.
    """
    self.get_application().dismiss()

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

    self._apply_overlay_margins()

  def _apply_overlay_margins(self):
    """
      Push the configured overlay margins (logical px) onto the layer surface.
      Re-applied on each fresh show so config edits take effect without a
      daemon restart.
    """
    mx = config.CFG["margin_x"]
    my = config.CFG["margin_y"]
    LayerShell.set_margin(self, LayerShell.Edge.TOP,    my)
    LayerShell.set_margin(self, LayerShell.Edge.BOTTOM, my)
    LayerShell.set_margin(self, LayerShell.Edge.LEFT,   mx)
    LayerShell.set_margin(self, LayerShell.Edge.RIGHT,  mx)

  # ----- action handlers -----
  def _on_backdrop_clicked(self, _gesture, _n_press, x, y):
    # did the click land in the drawer area? do nothing
    target = self.pick(x, y, Gtk.PickFlags.DEFAULT) # pylint: disable=no-member
    while target is not None:
      if target is self._root:
        return
      target = target.get_parent()

    # if it's outside the drawer? close ourselves
    self.dismiss()

  def _on_key_pressed(self, _kc, keyval, _kc2, _state):
    if ret := keyval == Gdk.KEY_Escape:
      if self._stack.get_visible_child_name() == "settings":
        # escape backs out of settings first
        self.show_launcher()

      else:
        # then dismisses the drawer
        self.dismiss()

    return ret
