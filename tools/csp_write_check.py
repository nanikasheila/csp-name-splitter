"""Write small .clip files to check by hand that CSP opens what we write.

Why: Only CLIP STUDIO PAINT itself can tell whether a written .clip is
     accepted. These files each test one writing step, so a failure points
     at the step that broke.
How: Copies the template's structure (the template file is only read) and
     writes, into ``out_dir``:

     - 01_roundtrip.clip   the template rebuilt without changes
     - 02_raster_fill.clip the template's raster layer filled with a test pattern
     - 03_raster_new.clip  a new raster layer with the test pattern on top

Usage::

    python tools/csp_write_check.py EMPTY_PAGE.clip OUT_DIR
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from name_splitter.csp.clip_editor import ClipEditor  # noqa: E402
from name_splitter.csp.container import open_sqlite_bytes, read_csf_container  # noqa: E402


def test_pattern(width: int, height: int) -> Image.Image:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    unit = min(width, height) // 10
    draw.rectangle((unit, unit, width - unit, height - unit), outline=(0, 0, 0, 255), width=unit // 10)
    draw.ellipse((width // 2 - 2 * unit, height // 2 - 2 * unit, width // 2 + 2 * unit, height // 2 + 2 * unit),
                 fill=(220, 40, 40, 255))
    draw.line((unit, unit, width - unit, height - unit), fill=(40, 80, 220, 160), width=unit // 5)
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("template")
    parser.add_argument("out_dir")
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    if out_dir.resolve() == Path(args.template).resolve().parent:
        print("out_dir must differ from the template folder", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    ClipEditor(args.template).save(out_dir / "01_roundtrip.clip")

    editor = ClipEditor(args.template)
    layer_id = editor.first_raster_layer()
    canvas = editor.db.execute("SELECT CanvasWidth, CanvasHeight, CanvasResolution, CanvasUnit FROM Canvas").fetchone()
    width, height = _canvas_px(canvas)
    editor.set_layer_image(layer_id, test_pattern(width, height))
    editor.save(out_dir / "02_raster_fill.clip")

    editor = ClipEditor(args.template)
    source = open_sqlite_bytes(read_csf_container(args.template).sqlite_bytes)
    new_id = editor.add_layer(source, editor.externals.get, editor.first_raster_layer(),
                              row_hook=lambda values: values.update(LayerName="書き出しテスト"))
    editor.append_to_folder(editor.root_id, new_id)
    editor.set_layer_image(new_id, test_pattern(width, height))
    editor.save(out_dir / "03_raster_new.clip")
    for path in sorted(out_dir.glob("0*.clip")):
        print(f"Wrote {path}")
    return 0


def _canvas_px(row: tuple[float, float, float, int]) -> tuple[int, int]:
    width, height, resolution, unit = row
    per_inch = {2: 25.4, 1: 2.54, 3: 1.0}.get(int(unit))
    if per_inch is None:
        return round(width), round(height)
    return round(width * resolution / per_inch), round(height * resolution / per_inch)


if __name__ == "__main__":
    raise SystemExit(main())
