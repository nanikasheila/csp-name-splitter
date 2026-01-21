from __future__ import annotations

from dataclasses import dataclass

from .config import MergeConfig
from .psd_read import LayerNode


@dataclass(frozen=True)
class LayerRef:
    name: str
    kind: str
    path: tuple[str, ...]
    visible: bool


@dataclass(frozen=True)
class MergeResult:
    outputs: dict[str, list[LayerRef]]
    unmatched: list[LayerRef]
    warnings: list[str]


def apply_merge_rules(layers: tuple[LayerNode, ...], cfg: MergeConfig) -> MergeResult:
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

    return MergeResult(outputs=outputs, unmatched=unmatched, warnings=warnings)


def _iter_layer_refs(layers: tuple[LayerNode, ...], include_hidden: bool) -> list[LayerRef]:
    refs: list[LayerRef] = []

    def walk(node: LayerNode, path: tuple[str, ...]) -> None:
        if not include_hidden and not node.visible:
            return
        current_path = path + (node.name,)
        refs.append(LayerRef(name=node.name, kind=node.kind, path=current_path, visible=node.visible))
        for child in node.children:
            walk(child, current_path)

    for layer in layers:
        walk(layer, ())
    return refs


def _match_rule(name: str, rules) -> object | None:
    for rule in rules:
        target = rule.group_name if rule.group_name is not None else rule.layer_name
        if target == name:
            return rule
    return None


def _warn_unused_rules(label: str, rules, outputs: dict[str, list[LayerRef]]) -> list[str]:
    warnings: list[str] = []
    matched_layers = {ref.name for refs in outputs.values() for ref in refs}
    for rule in rules:
        target = rule.group_name if rule.group_name is not None else rule.layer_name
        if target not in matched_layers:
            warnings.append(f"{label}: no match for {target}")
    return warnings
