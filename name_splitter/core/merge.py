from __future__ import annotations

from dataclasses import dataclass, field

from .config import MergeConfig, MergeRule
from .image_ops import ImageData, composite_layers
from .image_read import LayerNode, LayerPixels


@dataclass(frozen=True)
class LayerRef:
    # レイヤー参照（パスとピクセルを保持）
    name: str
    kind: str
    path: tuple[str, ...]
    visible: bool
    pixels: LayerPixels | None = None


@dataclass(frozen=True)
class MergeResult:
    # ルール適用結果と合成済み画像
    outputs: dict[str, list[LayerRef]]
    unmatched: list[LayerRef]
    warnings: list[str]
    output_images: dict[str, ImageData] = field(default_factory=dict)


def apply_merge_rules(
    layers: tuple[LayerNode, ...],
    cfg: MergeConfig,
    *,
    canvas_size: tuple[int, int] | None = None,
) -> MergeResult:
    # ルールマッチングと（必要なら）画像合成を実行
    outputs: dict[str, list[LayerRef]] = {}
    unmatched: list[LayerRef] = []

    layer_rules = list(cfg.layer_rules)
    group_rules = list(cfg.group_rules)

    for ref in _iter_layer_refs(layers, include_hidden=cfg.include_hidden_layers):
        if ref.kind == "group":
            rule = _match_rule(ref.name, group_rules)
        else:
            rule = _match_rule(ref.name, layer_rules)
        if rule is None:
            unmatched.append(ref)
            continue
        outputs.setdefault(rule.output_layer, []).append(ref)

    warnings: list[str] = []
    warnings.extend(_warn_unused_rules("merge.group_rules", group_rules, outputs))
    warnings.extend(_warn_unused_rules("merge.layer_rules", layer_rules, outputs))

    output_images = {}
    if canvas_size is not None:
        output_images = _build_output_images(
            layers, outputs, canvas_size=canvas_size, include_hidden=cfg.include_hidden_layers
        )

    return MergeResult(
        outputs=outputs, output_images=output_images, unmatched=unmatched, warnings=warnings
    )


def _iter_layer_refs(layers: tuple[LayerNode, ...], include_hidden: bool) -> list[LayerRef]:
    # レイヤーツリーをフラットな参照列に変換
    refs: list[LayerRef] = []

    def walk(node: LayerNode, path: tuple[str, ...]) -> None:
        if not include_hidden and not node.visible:
            return
        current_path = path + (node.name,)
        refs.append(
            LayerRef(
                name=node.name,
                kind=node.kind,
                path=current_path,
                visible=node.visible,
                pixels=node.pixels,
            )
        )
        for child in node.children:
            walk(child, current_path)

    for layer in layers:
        walk(layer, ())
    return refs


def _match_rule(name: str, rules: list[MergeRule]) -> MergeRule | None:
    """Find a matching rule by name.

    Why: Each layer/group name must be tested against all configured rules
         to determine which output layer it belongs to.
    How: Linear scan comparing the rule's group_name or layer_name against
         the given name. Returns the first match or None.
    """
    for rule in rules:
        target = rule.group_name if rule.group_name is not None else rule.layer_name
        if target == name:
            return rule
    return None


def _warn_unused_rules(label: str, rules, outputs: dict[str, list[LayerRef]]) -> list[str]:
    # 未使用ルールを警告として集計
    warnings: list[str] = []
    matched_layers = {ref.name for refs in outputs.values() for ref in refs}
    for rule in rules:
        target = rule.group_name if rule.group_name is not None else rule.layer_name
        if target not in matched_layers:
            warnings.append(f"{label}: no match for {target}")
    return warnings


def _build_output_images(
    layers: tuple[LayerNode, ...],
    outputs: dict[str, list[LayerRef]],
    *,
    canvas_size: tuple[int, int],
    include_hidden: bool,
) -> dict[str, ImageData]:
    # ルールに一致したレイヤーを合成して出力レイヤー画像を作成
    output_images: dict[str, ImageData] = {}
    leaf_refs = [
        ref
        for ref in _iter_layer_refs(layers, include_hidden=include_hidden)
        if ref.kind == "layer" and ref.pixels is not None
    ]
    for output_name, refs in outputs.items():
        layer_paths = {ref.path for ref in refs if ref.kind == "layer"}
        group_paths = {ref.path for ref in refs if ref.kind == "group"}
        composite_sources: list[tuple[ImageData, tuple[int, int]]] = []
        seen_paths: set[tuple[str, ...]] = set()
        for leaf_ref in leaf_refs:
            if leaf_ref.path in layer_paths:
                pass
            else:
                if not _has_ancestor(leaf_ref.path, group_paths):
                    continue
            if leaf_ref.path in seen_paths or leaf_ref.pixels is None:
                continue
            seen_paths.add(leaf_ref.path)
            pixels = leaf_ref.pixels
            x0, y0, _x1, _y1 = pixels.bbox
            composite_sources.append((pixels.image, (x0, y0)))
        if composite_sources:
            output_images[output_name] = composite_layers(canvas_size, composite_sources)
    return output_images


def _has_ancestor(path: tuple[str, ...], group_paths: set[tuple[str, ...]]) -> bool:
    # グループパスの子孫かどうかを判定
    for index in range(1, len(path)):
        if path[:index] in group_paths:
            return True
    return False
