# waydrawer: a GTK4 app drawer for Wayland

## TL;DR
- app grid + launcher bar for wayland compositors
  - search for apps
  - fall back to websearch
- inspired by the gnome app drawer that I couldn't find anywhere else
- tested on hyprland

## Features:
- Reads .desktop files via Gio.AppInfo (uses your system icon theme)
- Apps grouped by category (Internet, Development, Office, Media, etc.)
- Live filter as you type (matches name, generic name, keywords)
- Web search fallback when no apps match (Enter or click the row)
- URL loading in browser if the input looks like a URL
- Executes basic arithmetic in the search bar & copies results to clipboard
- Layer-shell overlay; Esc to close, Enter to launch first visible match

## Dependencies:
python-gobject gtk4 gtk4-layer-shell

## Install:
make install

## Keybindings
Hyprland hyprlang keybind:
bind = SUPER, Space, exec, waydrawer

Hyprland lua keybind:
hl.bind("SUPER + Space", hl.dsp.exec_cmd("waydrawer"))

## Configuration:
~/.config/waydrawer/config.toml
~/.config/waydrawer/style.css
