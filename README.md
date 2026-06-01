# waydrawer: a GTK4 app drawer for Wayland

## TL;DR
- app grid + launcher bar for wayland compositors
  - search for apps
  - do basic math
  - fall back to websearch
  - open a website
  - pin favorite apps
  - optional daemon mode for fast start up times
- inspired by the gnome app drawer that I couldn't find anywhere else
- tested on hyprland

## Features
- Reads .desktop files (cached between runs) to find all your apps
- Apps grouped by category (Internet, Office, etc.)
- Live filter as you type (matches name, generic name, keywords)
- Pin your favorite apps with a right click (appears first in app grid)
- Web search fallback when no apps match (Enter or click the row)
- URL loading in browser if the input looks like a URL
- Executes basic arithmetic in the search bar & copies results to clipboard
- Layer-shell overlay; Esc to close, Enter to launch first visible match
- Daemon mode using sockets that allows the client to open nearly instantly
- CSS styling of GTK components (with examples!)
- Config file for basic customization (like search fallback URL)

## Dependencies
Python:
- python 3.11+ (for tomllib)
- python-gobject, gtk4, gtk4-layer-shell, wl-clipboard, xdg-utils

On Ubuntu:
```
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-gtk4layershell-1.0 wl-clipboard xdg-utils
```

## Install
Build and copy result to ~/.local/bin/waydrawer
```
make install
```

## Keybindings

Hyprland hyprlang keybind
```
bind = SUPER, Space, exec, waydrawer
```
Hyprland lua keybind
```
hl.bind("SUPER + Space", hl.dsp.exec_cmd("waydrawer"))
```

## Configuration
Examples are
- config/config.toml
- config/style.css

Your files live at
- ~/.config/waydrawer/config.toml
- ~/.config/waydrawer/style.css

## Running waydrawer
<pre>
%% waydrawer -h
usage: waydrawer [-h] [-d | -q]

GTK4 app drawer for Wayland.

options:
  -h, --help    show this help message and exit
  -d, --daemon  run as a daemon: build the drawer once, show/hide on request
  -q, --quit    tell a running daemon to exit
</pre>
