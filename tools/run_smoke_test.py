from __future__ import annotations

from pathlib import Path

from name_splitter.core.config import Config, GridConfig, OutputConfig
from name_splitter.core.grid import compute_cells
from name_splitter.core.psd_read import PsdInfo
from name_splitter.core.render import write_plan

TEST_ENV_DIR = Path(__file__).resolve().parents[1] / "test_env"


def read_ppm_size(path: Path) -> tuple[int, int]:
    with path.open("r", encoding="utf-8") as handle:
        if handle.readline().strip() != "P3":
            raise ValueError("Only ASCII P3 PPM is supported for smoke test")
        line = handle.readline()
        while line.startswith("#"):
            line = handle.readline()
        width_str, height_str = line.split()
        return int(width_str), int(height_str)


def main() -> None:
    sample_ppm = TEST_ENV_DIR / "sample.ppm"
    if not sample_ppm.exists():
        raise FileNotFoundError("sample.ppm not found; run tools/create_test_env.py")
    cfg = Config(
        grid=GridConfig(rows=4, cols=4, order="rtl_ttb", margin_px=0, gutter_px=0),
        output=OutputConfig(out_dir="output"),
    )
    width, height = read_ppm_size(sample_ppm)
    info = PsdInfo(width=width, height=height)
    cells = compute_cells(info.width, info.height, cfg.grid)
    out_dir = TEST_ENV_DIR / cfg.output.out_dir
    plan = write_plan(out_dir, info, cells, cfg, list(range(len(cells))))
    print(f"Wrote plan: {plan.manifest_path}")


if __name__ == "__main__":
    main()
