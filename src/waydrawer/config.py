# ----------- Config ----------------------------------------------------------
#
# XXX gc3: fixme
#
import os

from pathlib import Path
from gi.repository import GLib

APP_NAME = "waydrawer"
CONFIG_DIR = Path(GLib.get_user_config_dir()) / APP_NAME

SEARCH_URL = os.environ.get(
  "WAYDRAWER_SEARCH_URL",
  "https://duckduckgo.com/?q={}",
)

# .desktop Categories= -> display bucket. First match wins.
CATEGORY_MAP = {
  "AudioVideo": "Media", "Audio": "Media", "Video": "Media",
  "Player": "Media", "Music": "Media",
  "Development": "Development", "IDE": "Development",
  "Education": "Education",
  "Game": "Games",
  "Graphics": "Graphics", "Photography": "Graphics",
  "Network": "Internet", "WebBrowser": "Internet",
  "Email": "Internet", "Chat": "Internet", "InstantMessaging": "Internet",
  "Office": "Office", "WordProcessor": "Office", "Spreadsheet": "Office",
  "Science": "Science",
  "Settings": "System", "System": "System",
  "Utility": "Utilities", "Accessories": "Utilities",
}

CATEGORY_ORDER = [
  "Internet", "Development", "Office", "Graphics", "Media",
  "Games", "Utilities", "System", "Education", "Science", "Other",
]
