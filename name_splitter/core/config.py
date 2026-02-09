from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .errors import ConfigError

ALLOWED_GRID_ORDERS = {"rtl_ttb", "ltr_ttb"}
ALLOWED_ON_EXCEED = {"error"}
ALLOWED_OUTPUT_LAYOUTS = {"pages", "layers"}


@dataclass(frozen=True)
class InputConfig:
    image_path: str = ""


@dataclass(frozen=True)
class GridConfig:
    rows: int = 4
    cols: int = 4
    order: str = "rtl_ttb"
    margin_px: int = 0  # Deprecated: use margin_top_px, etc.
    margin_top_px: int = 0
    margin_bottom_px: int = 0
    margin_left_px: int = 0
    margin_right_px: int = 0
    gutter_px: int = 0
    dpi: int = 300
    page_width_px: int = 0  # 0 means use default
    page_height_px: int = 0


@dataclass(frozen=True)
class MergeRule:
    group_name: str | None = None
    layer_name: str | None = None
    output_layer: str = ""


@dataclass(frozen=True)
class MergeConfig:
    group_rules: tuple[MergeRule, ...] = field(default_factory=tuple)
    layer_rules: tuple[MergeRule, ...] = field(default_factory=tuple)
    include_hidden_layers: bool = False


@dataclass(frozen=True)
class OutputConfig:
    out_dir: str = ""
    page_basename: str = "page_{page:03d}"
    layer_stack: tuple[str, ...] = ("flat",)
    raster_ext: str = "png"
    container: str = "png"
    layout: str = "layers"


@dataclass(frozen=True)
class LimitsConfig:
    max_dim_px: int = 30000
    on_exceed: str = "error"


@dataclass(frozen=True)
class Config:
    version: int = 1
    input: InputConfig = field(default_factory=InputConfig)
    grid: GridConfig = field(default_factory=GridConfig)
    merge: MergeConfig = field(default_factory=MergeConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    limits: LimitsConfig = field(default_factory=LimitsConfig)


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{label} must be a mapping")
    return value


def _parse_rules(values: Iterable[dict[str, Any]] | None, label: str) -> tuple[MergeRule, ...]:
    if values is None:
        return tuple()
    rules: list[MergeRule] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise ConfigError(f"{label}[{index}] must be a mapping")
        output_layer = str(item.get("output_layer", "")).strip()
        if not output_layer:
            raise ConfigError(f"{label}[{index}].output_layer is required")
        group_name = item.get("group_name")
        layer_name = item.get("layer_name")
        if group_name is None and layer_name is None:
            raise ConfigError(f"{label}[{index}] requires group_name or layer_name")
        rules.append(
            MergeRule(
                group_name=str(group_name) if group_name is not None else None,
                layer_name=str(layer_name) if layer_name is not None else None,
                output_layer=output_layer,
            )
        )
    return tuple(rules)


def load_config(path: str | Path) -> Config:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Config not found: {config_path}")
    
    suffix = config_path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ConfigError("PyYAML is required to load YAML config files") from exc
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    elif suffix == ".json":
        import json
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        raise ConfigError(f"Unsupported config file format: {suffix}. Use .yaml, .yml, or .json")
    
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a mapping")

    input_section = _require_mapping(raw.get("input"), "input")
    grid_section = _require_mapping(raw.get("grid"), "grid")
    merge_section = _require_mapping(raw.get("merge"), "merge")
    output_section = _require_mapping(raw.get("output"), "output")
    limits_section = _require_mapping(raw.get("limits"), "limits")

    merge = MergeConfig(
        group_rules=_parse_rules(merge_section.get("group_rules"), "merge.group_rules"),
        layer_rules=_parse_rules(merge_section.get("layer_rules"), "merge.layer_rules"),
        include_hidden_layers=bool(merge_section.get("include_hidden_layers", False)),
    )

    input_path = input_section.get("image_path", input_section.get("psd_path", ""))
    
    # Backward compatibility: if margin_px exists but 4-direction margins don't, apply to all
    legacy_margin = int(grid_section.get("margin_px", 0))
    margin_top = int(grid_section.get("margin_top_px", legacy_margin))
    margin_bottom = int(grid_section.get("margin_bottom_px", legacy_margin))
    margin_left = int(grid_section.get("margin_left_px", legacy_margin))
    margin_right = int(grid_section.get("margin_right_px", legacy_margin))
    
    config = Config(
        version=int(raw.get("version", 1)),
        input=InputConfig(image_path=str(input_path)),
        grid=GridConfig(
            rows=int(grid_section.get("rows", 4)),
            cols=int(grid_section.get("cols", 4)),
            order=str(grid_section.get("order", "rtl_ttb")),
            margin_px=legacy_margin,
            margin_top_px=margin_top,
            margin_bottom_px=margin_bottom,
            margin_left_px=margin_left,
            margin_right_px=margin_right,
            gutter_px=int(grid_section.get("gutter_px", 0)),
            dpi=int(grid_section.get("dpi", 300)),
            page_width_px=int(grid_section.get("page_width_px", 0)),
            page_height_px=int(grid_section.get("page_height_px", 0)),
        ),
        merge=merge,
        output=OutputConfig(
            out_dir=str(output_section.get("out_dir", "")),
            page_basename=str(output_section.get("page_basename", "page_{page:03d}")),
            layer_stack=tuple(
                output_section.get("layer_stack", ("flat",))
            ),
            raster_ext=str(output_section.get("raster_ext", "png")),
            container=str(output_section.get("container", "png")),
            layout=str(output_section.get("layout", "layers")),
        ),
        limits=LimitsConfig(
            max_dim_px=int(limits_section.get("max_dim_px", 30000)),
            on_exceed=str(limits_section.get("on_exceed", "error")),
        ),
    )
    validate_config(config)
    return config


def load_default_config() -> Config:
    default_path = Path(__file__).resolve().parents[2] / "resources" / "default_config.yaml"
    return load_config(default_path)


def validate_config(cfg: Config) -> None:
    if cfg.version != 1:
        raise ConfigError(f"Unsupported config version: {cfg.version}")
    if cfg.grid.rows <= 0 or cfg.grid.cols <= 0:
        raise ConfigError("grid.rows and grid.cols must be positive")
    if cfg.grid.margin_px < 0 or cfg.grid.gutter_px < 0:
        raise ConfigError("grid.margin_px and grid.gutter_px must be >= 0")
    if cfg.grid.margin_top_px < 0 or cfg.grid.margin_bottom_px < 0:
        raise ConfigError("grid.margin_top_px and grid.margin_bottom_px must be >= 0")
    if cfg.grid.margin_left_px < 0 or cfg.grid.margin_right_px < 0:
        raise ConfigError("grid.margin_left_px and grid.margin_right_px must be >= 0")
    if cfg.grid.dpi <= 0:
        raise ConfigError("grid.dpi must be positive")
    if cfg.grid.page_width_px < 0 or cfg.grid.page_height_px < 0:
        raise ConfigError("grid.page_width_px and grid.page_height_px must be >= 0")
    if cfg.grid.order not in ALLOWED_GRID_ORDERS:
        raise ConfigError(f"grid.order must be one of {sorted(ALLOWED_GRID_ORDERS)}")
    if cfg.limits.max_dim_px <= 0:
        raise ConfigError("limits.max_dim_px must be positive")
    if cfg.limits.on_exceed not in ALLOWED_ON_EXCEED:
        raise ConfigError(f"limits.on_exceed must be one of {sorted(ALLOWED_ON_EXCEED)}")
    if not cfg.output.layer_stack:
        raise ConfigError("output.layer_stack must not be empty")
    if cfg.output.layout not in ALLOWED_OUTPUT_LAYOUTS:
        raise ConfigError(f"output.layout must be one of {sorted(ALLOWED_OUTPUT_LAYOUTS)}")
