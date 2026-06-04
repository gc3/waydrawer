# ----------- waydrawer entry point --------------------------------------------
"""
  waydrawer: GTK4 app drawer for Wayland

  Nothing GTK is imported on the bare-invocation client path, so waking the
  daemon costs an interpreter start + a socket write, not a full gi load.
"""
# pylint: disable=import-outside-toplevel
# pylint: disable=consider-using-with
from __future__ import annotations

import os
import sys
import socket
import argparse
import setproctitle

setproctitle.setproctitle("waydrawer")

_RUNTIME = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
SOCK_PATH = f"{_RUNTIME}/waydrawer.sock"
LOCK_PATH = f"{_RUNTIME}/waydrawer.lock"


def _send(cmd: bytes) -> bool:
  """
    Send one command to a running daemon. True if one was listening.
  """
  s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
  try:
    s.connect(SOCK_PATH)
    s.sendall(cmd)
    return True

  except (FileNotFoundError, ConnectionRefusedError):
    # no daemon, or a stale socket file
    return False

  finally:
    s.close()


def _ensure_preload():
  """
    Re-exec once with LD_PRELOAD set (guarded so it only fires on the first pass).

    Linker must load libgtk4-layer-shell.so before libwayland-client.so.
    https://github.com/wmww/gtk4-layer-shell/blob/main/linking.md
  """
  preload = "/usr/lib/x86_64-linux-gnu/libgtk4-layer-shell.so"
  if os.path.exists(preload) and "gtk4-layer-shell" not in os.environ.get("LD_PRELOAD", ""):
    os.environ["LD_PRELOAD"] = preload
    os.environ["PYTHONPATH"] = ":".join(sys.path)
    os.execv(sys.executable, [sys.executable] + sys.argv)


def _daemonize():
  """
    Double-fork so the daemon detaches from the launching shell/keybind.
  """
  if os.fork() > 0:
    os._exit(0)

  os.setsid()
  if os.fork() > 0:
    os._exit(0)

  devnull = os.open(os.devnull, os.O_RDWR)
  for fd in (0, 1, 2):
    os.dup2(devnull, fd)


def _run_gtk(daemon_mode: bool) -> int:
  """
    Run the waydrawer ui and do so in daemon mode if necessary. Note: We do some
    imports here locally, so we don't spend that time during the fast path.
  """
  import fcntl

  _ensure_preload() # required bugfix

  # single-instance guard — the daemon (or a one-shot run) holds this lock.
  lock_fd = open(LOCK_PATH, "wb")
  try:
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

  except BlockingIOError:
    print("[waydrawer] already running. Exiting...", file=sys.stderr)
    return 0

  #if daemon_mode:
    #_daemonize()

  # We make the app to pre-load the ui for the future callers. We pass None when
  # running since we parsed and all the args in main().
  from waydrawer.app import WayDrawerApp
  app = WayDrawerApp(SOCK_PATH, daemon_mode, lock_fd)
  return app.run(None)

def _build_parser() -> argparse.ArgumentParser:
  """
    Use argparse to ... parse the args.
  """
  parser = argparse.ArgumentParser(
    prog = "waydrawer",
    description = "GTK4 app drawer for Wayland.",
    formatter_class = argparse.RawDescriptionHelpFormatter,
  )

  group = parser.add_mutually_exclusive_group()
  group.add_argument(
    "-d", "--daemon",
    action="store_true",
    help="run as a daemon: build the drawer once, show/hide on request"
  )
  group.add_argument(
    "-q", "--quit",
    action="store_true",
    help="tell a running daemon to exit"
  )
  group.add_argument(
    "-t", "--toggle",
    action="store_true",
    help="toggle the waydrawer ui"
  )

  return parser


def main() -> int:
  """ is yo maaan, on da floor """
  args = _build_parser().parse_args()

  # if he ain't ... lemme know
  if args.quit:
    _send(b"quit\n")
    return 0

  # let me see if you can run it, run it
  if not args.daemon:
    if args.toggle and _send(b"toggle\n"):
      return 0

    if _send(b"show\n"):
      return 0

  # indeed i can run it, run it
  return _run_gtk(args.daemon)


if __name__ == "__main__":
  sys.exit(main())
