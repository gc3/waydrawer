# ----------- waydrawer GTK Application ----------------------------------------
"""
  The long-lived Gtk.Application. In daemon mode it builds the drawer once,
  holds the main loop alive, and shows/hides in response to socket commands
  instead of quitting. In one-shot mode it behaves like the old app.
"""
# pylint: disable=arguments-differ
# pylint: disable=wrong-import-position
from __future__ import annotations

import os
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("GioUnix", "2.0")
from gi.repository import GLib, Gtk, Gio, Gtk4LayerShell as LayerShell

from waydrawer import ui
from waydrawer import style


class WayDrawerApp(Gtk.Application):
  """
    main Gtk application; one-shot or daemon
  """

  def __init__(self, sock_path: str, daemon: bool, lock_fd,
               start_in_settings: bool = False):
    super().__init__(
      application_id = "io.github.gc3.waydrawer",
      flags = Gio.ApplicationFlags.NON_UNIQUE,
    )

    self._sock_path = sock_path
    self._daemon = daemon
    self._lock_fd = lock_fd
    self._start_in_settings = start_in_settings  # one-shot only; daemon uses the socket
    self._window = None
    self._service = None

  # ----- window -----
  def show(self, settings: bool = False):
    """
      show the waydrawer ui, optionally landing on the settings view
    """
    if self._window is None:
      return

    self._window.set_visible(True)
    self._window.present()

    # window must be mapped before we touch focus/layout, so defer to idle
    if settings:
      GLib.idle_add(lambda: (self._window.show_settings(), False)[1])

    else:
      GLib.idle_add(lambda: (self._window.reset_for_show(), False)[1])


  def dismiss(self):
    """
      Called by the window instead of quit(): hide if daemon, else quit.
    """
    if self._daemon and self._window is not None:
      self._window.set_visible(False)

    else:
      # window gone -> use count drops -> run() returns once any in-flight
      # launch releases its hold. quit() would kill pending launches.
      self._window.destroy()


  # ----- lifecycle -----
  def do_startup(self):
    """
      Start me up! (daemon mode only)
    """
    Gtk.Application.do_startup(self)

    if not LayerShell.is_supported():
      print(
        "[waydrawer] this compositor does not support wlr-layer-shell; "
        "waydrawer requires a wlroots-based compositor (Sway, Hyprland, niri, …).",
        file=sys.stderr,
      )
      sys.exit(1)

    style.setup_css()

    # Once you start me up, I never stop!
    if self._daemon:
      self.hold()                     # stay alive with no visible window
      self._window = ui.Drawer(self)  # pre initialize the ui fo future callers
      self._start_socket()            # await callers

  def do_activate(self):
    """
      activate the ui layer (one-shot mode only)
    """
    if self._daemon:
      return

    # build + show now
    self._window = ui.Drawer(self)
    self.show(self._start_in_settings)


  # ----- socket -----
  def _start_socket(self):
    """
      daemon mode: begin waiting for incoming messages
    """
    try:
      # we hold the lock, so any existing socket file is stale — remove it.
      os.unlink(self._sock_path)

    except FileNotFoundError:
      pass

    addr = Gio.UnixSocketAddress.new(self._sock_path)
    self._service = Gio.SocketService.new()
    self._service.add_address(
      addr,
      Gio.SocketType.STREAM,
      Gio.SocketProtocol.DEFAULT,
      None
    )
    self._service.connect("incoming", self._on_incoming)
    self._service.start()


  def _on_incoming(self, _service, connection, _source):
    """
      daemon mode: handle an incomming connection.

        MUST NOT block here. Ref the connection (it's unreffed when we return)
        and read asynchronously; the callback runs later on the main loop.
    """
    connection.get_input_stream().read_bytes_async(
      64,
      GLib.PRIORITY_DEFAULT,
      None,
      self._on_read, connection
    )

    # we took ownership of this connection
    return True

  def _on_read(self, stream, result, connection):
    """
      daemon mode: react to an incoming command
    """
    try:
      data = stream.read_bytes_finish(result)

    except GLib.Error:
      connection.close_async(GLib.PRIORITY_DEFAULT, None, None)
      return

    cmd = data.get_data().decode("utf-8", "replace").strip()
    if cmd == "show":
      self.show()

    elif cmd == "settings":
      self.show(settings = True)

    elif cmd == "toggle":
      if (self._window is not None and self._window.get_visible()):
        self.dismiss()

      else:
        self.show()

    elif cmd == "quit":
      self.quit()

    # close our end so the client's connect()/send() completes cleanly
    connection.close_async(GLib.PRIORITY_DEFAULT, None, None)
