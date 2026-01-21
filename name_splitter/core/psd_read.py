from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import PsdReadError


@dataclass(frozen=True)
class PsdInfo:
    width: int
    height: int


@dataclass(frozen=True)
class LayerNode:
    name: str
    kind: str
    visible: bool
    children: tuple["LayerNode", ...] = ()


@dataclass(frozen=True)
class PsdDocument:
    info: PsdInfo
    layers: tuple[LayerNode, ...]


def read_psd(path: str | Path) -> PsdInfo:
    psd = _open_psd(path)
    return PsdInfo(width=int(psd.width), height=int(psd.height))


def read_psd_document(path: str | Path) -> PsdDocument:
    psd = _open_psd(path)
    info = PsdInfo(width=int(psd.width), height=int(psd.height))
    layers = tuple(_build_layers(psd))
    return PsdDocument(info=info, layers=layers)


def _open_psd(path: str | Path):
    psd_path = Path(path)
    if not psd_path.exists():
        raise PsdReadError(f"PSD not found: {psd_path}")
    try:
        from psd_tools import PSDImage  # type: ignore
    except ImportError as exc:
        raise PsdReadError("psd-tools is required to read PSD files") from exc
    try:
        return PSDImage.open(psd_path)
    except Exception as exc:  # noqa: BLE001
        raise PsdReadError(f"Failed to read PSD: {psd_path}") from exc


def _build_layers(psd) -> list[LayerNode]:
    nodes: list[LayerNode] = []
    for layer in psd:
        nodes.append(_build_layer_node(layer))
    return nodes


def _build_layer_node(layer) -> LayerNode:
    name = getattr(layer, "name", "")
    visible = bool(getattr(layer, "visible", True))
    if getattr(layer, "is_group", lambda: False)():
        children = tuple(_build_layer_node(child) for child in layer)
        return LayerNode(name=name, kind="group", visible=visible, children=children)
    return LayerNode(name=name, kind="layer", visible=visible, children=())
