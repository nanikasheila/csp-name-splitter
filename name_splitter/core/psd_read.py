from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import PsdReadError
from .image_ops import ImageData


@dataclass(frozen=True)
class PsdInfo:
    # PSDの全体サイズ
    width: int
    height: int


@dataclass(frozen=True)
class LayerPixels:
    # レイヤーの配置矩形とピクセル情報
    bbox: tuple[int, int, int, int]
    image: ImageData


@dataclass(frozen=True)
class LayerNode:
    # レイヤー/グループの構造情報
    name: str
    kind: str
    visible: bool
    children: tuple["LayerNode", ...] = ()
    pixels: LayerPixels | None = None


@dataclass(frozen=True)
class PsdDocument:
    info: PsdInfo
    layers: tuple[LayerNode, ...]


def read_psd(path: str | Path) -> PsdInfo:
    # PSDのメタ情報だけ読み込む
    psd = _open_psd(path)
    return PsdInfo(width=int(psd.width), height=int(psd.height))


def read_psd_document(path: str | Path) -> PsdDocument:
    # PSD全体とレイヤー構造を読み込む
    psd = _open_psd(path)
    info = PsdInfo(width=int(psd.width), height=int(psd.height))
    layers = tuple(_build_layers(psd))
    return PsdDocument(info=info, layers=layers)


def _open_psd(path: str | Path):
    # PSDファイルの存在確認と読み込み
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
    # psd-toolsのレイヤー列をLayerNodeに変換
    nodes: list[LayerNode] = []
    for layer in psd:
        nodes.append(_build_layer_node(layer))
    return nodes


def _build_layer_node(layer) -> LayerNode:
    # レイヤー/グループのノードを構築
    name = getattr(layer, "name", "")
    visible = bool(getattr(layer, "visible", True))
    if getattr(layer, "is_group", lambda: False)():
        children = tuple(_build_layer_node(child) for child in layer)
        return LayerNode(name=name, kind="group", visible=visible, children=children)
    pixels = _read_layer_pixels(layer)
    return LayerNode(name=name, kind="layer", visible=visible, children=(), pixels=pixels)


def _read_layer_pixels(layer) -> LayerPixels | None:
    # レイヤーのピクセルを抽出（取得できない場合はNone）
    has_pixels = getattr(layer, "has_pixels", True)
    if callable(has_pixels):
        has_pixels = has_pixels()
    if not has_pixels:
        return None
    bbox = getattr(layer, "bbox", None)
    if not bbox:
        return None
    try:
        image = layer.composite()
    except Exception:  # noqa: BLE001
        image = None
    if image is None:
        try:
            image = layer.topil()
        except Exception:  # noqa: BLE001
            return None
    pixels = ImageData.from_pil(image)
    bbox_tuple = (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
    return LayerPixels(bbox=bbox_tuple, image=pixels)
