# ----------- ui Settings View -------------------------------------------------
"""
  The settings view is where the user can update their shortcuts and
  configuration variables in the ui instead of the config files.
"""
from __future__ import annotations

# pylint: disable=wrong-import-position
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from waydrawer import config
from waydrawer import shortcuts

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
