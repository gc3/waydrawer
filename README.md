# waydrawer: a GTK4 app drawer for Wayland

An app grid + launcher bar for Wayland compositors — search your apps, pin
favorites, do quick math, open URLs, fall back to web search, and run your own
`xdg-open` shortcuts.

Inspired by the GNOME app drawer, which I couldn't find a standalone version of anywhere else.

Tested on Hyprland.

## What it does

- Search your installed apps, grouped by category
- Pin favorite apps to the top
- Do basic arithmetic right in the search bar (result copied to the clipboard)
- Open a URL in your browser if the input looks like one
- Fall back to a web search when nothing else matches
- Save named **shortcuts** that get handed to `xdg-open`
- Edit config and shortcuts from a built-in **settings** view
- Optional **daemon mode** for near-instant open times

## Features

- Reads `.desktop` files (cached between runs) to find all your apps
- Apps grouped by category (Internet, Office, etc.)
- Live filter as you type — matches name, generic name, and keywords
- Pin/unpin a favorite with a right-click; favorites appear first
- Web-search fallback when no app matches (Enter, or click the row)
- Opens the input in your browser when it looks like a URL
- Evaluates basic arithmetic in the search bar and copies the result
- Settings view (gear icon, or `waydrawer --settings`) for editing config
  values and shortcuts without leaving the drawer
- Shortcuts are plain TOML — hand-edit them or use the settings view; comments
  you add by hand are preserved
- Layer-shell overlay: `Esc` closes (or backs out of settings first), `Enter`
  launches the first visible match
- Daemon mode over a Unix socket so the client opens almost instantly
- CSS styling of the GTK components (with examples)
- TOML config file for basic customization (columns, icon size, search URL, …)

## Dependencies

Runtime:

- Python 3.11+
- PyGObject, GTK4, gtk4-layer-shell
- `wl-clipboard` (clipboard writes), `xdg-utils` (`xdg-open` for shortcuts)

`tomlkit` is vendored into the build, so you don't need to install it.

On Ubuntu:

```sh
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-gtk4layershell-1.0 wl-clipboard xdg-utils
```

## Install

Builds the zipapp (vendoring `tomlkit`) and installs it to `~/.local/bin/waydrawer`:

```sh
make install
```

Override the location with `PREFIX` if you like: `make install PREFIX=/usr/local`.

## Keybindings

Hyprland (hyprlang):

```
bind = SUPER, Space, exec, waydrawer
```

Hyprland (Lua):

```lua
hl.bind("SUPER + Space", hl.dsp.exec_cmd("waydrawer"))
```

## Configuration

Your files live in `~/.config/waydrawer/`:

- `config.toml` — basic options (columns, icon size, search-fallback URL, …)
- `shortcuts.toml` — your `name = "target"` shortcuts (each target is handed to `xdg-open`)
- `style.css` — CSS for the GTK widgets
- `favorites.json` — pinned apps; managed automatically, no need to edit

`config.toml` and `shortcuts.toml` are meant to be edited by hand *or* through
the in-app settings view — either way, comments and formatting survive. The
favorites file and the app cache are machine-managed JSON.

Example files to copy from are in `config/`:

- `config/config.toml`
- `config/shortcuts.toml`
- `config/style.css`

## Running waydrawer

```
$ waydrawer -h
usage: waydrawer [-h] [-d | -q | -t | -s]

GTK4 app drawer for Wayland.

options:
  -h, --help      show this help message and exit
  -d, --daemon    run as a daemon: build the drawer once, show/hide on request
  -q, --quit      tell a running daemon to exit
  -t, --toggle    toggle the waydrawer ui
  -s, --settings  open waydrawer on the settings view
```

With a daemon running, `waydrawer` (or `--toggle`) shows the drawer instantly;
`--settings` opens it straight to the settings view.

Without a daemon, each invocation is a slower, one-shot launch.
