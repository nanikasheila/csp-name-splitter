from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import PsdReadError


@dataclass(frozen=True)
class PsdInfo:
    width: int
    height: int


def read_psd(path: str | Path) -> PsdInfo:
    psd_path = Path(path)
    if not psd_path.exists():
        raise PsdReadError(f"PSD not found: {psd_path}")
    try:
        from psd_tools import PSDImage  # type: ignore
    except ImportError as exc:
        raise PsdReadError("psd-tools is required to read PSD files") from exc
    try:
        psd = PSDImage.open(psd_path)
    except Exception as exc:  # noqa: BLE001
        raise PsdReadError(f"Failed to read PSD: {psd_path}") from exc
    return PsdInfo(width=int(psd.width), height=int(psd.height))
