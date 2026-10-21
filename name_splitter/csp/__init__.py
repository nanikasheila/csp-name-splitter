"""Read-only access to CLIP STUDIO PAINT files (.clip / .cmc)."""
from .clip_reader import ClipCanvas, ClipDocument, ClipLayer, read_clip
from .cmc_reader import CmcDefaultPage, CmcPage, CmcProject, read_cmc
from .errors import CspFormatError
from .inspect import inspect_file

__all__ = [
    "ClipCanvas",
    "ClipDocument",
    "ClipLayer",
    "CmcDefaultPage",
    "CmcPage",
    "CmcProject",
    "CspFormatError",
    "inspect_file",
    "read_clip",
    "read_cmc",
]
