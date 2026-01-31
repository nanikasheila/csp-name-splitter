from __future__ import annotations

from pathlib import Path

from name_splitter.core.config import Config, GridConfig, OutputConfig
from name_splitter.core.grid import compute_cells
from name_splitter.core.image_read import ImageInfo
from name_splitter.core.render import write_plan

TEST_ENV_DIR = Path(__file__).resolve().parents[1] / "test_env"


def read_image_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Pillow is required to read PNG files") from exc
    with Image.open(path) as image:
        return image.size


def main() -> None:
    sample_png = TEST_ENV_DIR / "sample.png"
    if not sample_png.exists():
        raise FileNotFoundError("sample.png not found; run tools/create_test_env.py")
    cfg = Config(
        grid=GridConfig(rows=4, cols=4, order="rtl_ttb", margin_px=0, gutter_px=0),
        output=OutputConfig(out_dir="output"),
    )
    width, height = read_image_size(sample_png)
    info = ImageInfo(width=width, height=height)
    cells = compute_cells(info.width, info.height, cfg.grid)
    out_dir = TEST_ENV_DIR / cfg.output.out_dir
    plan = write_plan(out_dir, info, cells, cfg, list(range(len(cells))))
    print(f"Wrote plan: {plan.manifest_path}")


if __name__ == "__main__":
    main()
