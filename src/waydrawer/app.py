#Wrapper around cached .desktop data. Same surface as Gio.DesktopAppInfo
#where it matters, backed by a dict — no parsing on construction.

from dataclasses import dataclass, field, asdict
from typing import List, Optional
from gi.repository import Gtk, Gdk, Gio


@dataclass
class App:
    id: str
    filename: str
    name: str
    generic_name: str = ""
    comment: str = ""
    icon: str = ""
    commandline: str = ""
    categories: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

    # --- methods that mirror the old DesktopAppInfo API ---

    def get_id(self) -> str:
        return self.id

    def get_display_name(self) -> str:
        return self.name

    def get_name(self) -> str:
        return self.name

    def get_generic_name(self) -> str:
        return self.generic_name

    def get_description(self) -> str:
        return self.comment

    def get_commandline(self) -> str:
        return self.commandline

    def get_categories(self) -> List[str]:
        return self.categories

    def get_keywords(self) -> List[str]:
        return self.keywords

    def get_icon(self) -> Optional[Gio.Icon]:
      """Returns a Gio.Icon (themed or file), or None if no icon set."""
      if not self.icon:
          return None

      if self.icon.startswith("/"):
          return Gio.FileIcon.new(Gio.File.new_for_path(self.icon))

      return Gio.ThemedIcon.new(self.icon)
    """
    def get_icon(self, size: int = 64) -> Gtk.Image:
        # Returns a Gtk.Image ready to drop into a widget tree.
        if not self.icon:
            return Gtk.Image.new_from_icon_name("application-x-executable")
        if self.icon.startswith("/"):
            return Gtk.Image.new_from_file(self.icon)
        theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        paintable = theme.lookup_icon(
            self.icon, None, size, 1,
            Gtk.TextDirection.NONE,
            Gtk.IconLookupFlags.FORCE_REGULAR,
        )
        img = Gtk.Image.new_from_paintable(paintable)
        img.set_pixel_size(size)
        return img
        """

    def launch(self) -> bool:
        """Reconstruct DesktopAppInfo and launch. Parse cost paid once, on use."""
        info = Gio.DesktopAppInfo.new_from_filename(self.filename)
        if info is None:
            return False
        return info.launch([], None)

    # --- serialization ---

    @classmethod
    def from_dict(cls, d: dict) -> "App":
        return cls(**d)

    def to_dict(self) -> dict:
        return asdict(self)
