# ----------- DesktopAppInfo Wrapper -------------------------------------------
"""
  This is a wrapper around cached .desktop data. Same surface as Gio.DesktopAppInfo
  where it matters, backed by a dict — no parsing on construction. We create
  this indirection so the caller doesn't have to know if this is a cached set of
  app data or loaded by reading the .desktop file.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from typing import List, Optional
from gi.repository import Gio

@dataclass
class AppInfo:
  """
    Cached facade mimicking Gio.DesktopAppInfo
  """

  # pylint: disable=too-many-instance-attributes
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
  #   pylint: disable=missing-function-docstring
  #   pylint: disable=multiple-statements
  def get_id(self) -> str:                return self.id
  def get_display_name(self) -> str:      return self.name
  def get_name(self) -> str:              return self.name
  def get_generic_name(self) -> str:      return self.generic_name
  def get_description(self) -> str:       return self.comment
  def get_commandline(self) -> str:       return self.commandline
  def get_categories(self) -> List[str]:  return self.categories
  def get_keywords(self) -> List[str]:    return self.keywords

  def get_icon(self) -> Optional[Gio.Icon]:
    """
      Returns a Gio.Icon (themed or file), or None if no icon set.
    """
    if not self.icon:
      return None

    if self.icon.startswith("/"):
      return Gio.FileIcon.new(Gio.File.new_for_path(self.icon))

    return Gio.ThemedIcon.new(self.icon)

  def launch(self, files=None, context=None) -> bool:
    """
      Reconstruct DesktopAppInfo and launch. Parse cost paid once, on use.
    """
    info = Gio.DesktopAppInfo.new_from_filename(self.filename)
    if info is None:
      return False

    return info.launch(files or [], context)

  # --- serialization ---
  @classmethod
  def from_dict(cls, d: dict) -> "AppInfo":
    # ignore unknown keys so a schema-drifted cache entry degrades gracefully
    # instead of raising TypeError; missing required keys still raise (caught).
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in known})

  def to_dict(self) -> dict:
    return asdict(self)
