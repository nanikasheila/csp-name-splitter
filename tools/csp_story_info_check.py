"""Write variants of a page to find where CSP takes the 作品情報 text from.

Why: Pages written with ``split --story-index`` carry the new episode in the
     .cmc, the Canvas row and the story info layer's text, yet CSP EX 5.1.4
     still showed the template's episode. Each variant below changes only
     one of these places, so opening them one by one shows which one CSP
     reads.
How: Copies the template page (only read) into ``out_dir``:

     - s1_control.clip  only new file id / layer uuids
     - s2_string.clip   the story info layer's TextLayerString → "テストテスト 4話"
     - s3_canvas.clip   Canvas ComicStoryStoryName → "テストテスト", ComicStoryStoryIndex → 4
     - s4_both.clip     s2 and s3 together
     - s5_no_render.clip s4 plus the story info layers' render mipmaps cleared

Usage::

    python tools/csp_story_info_check.py EMPTY_PAGE.clip OUT_DIR
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from name_splitter.csp.clip_editor import ClipEditor  # noqa: E402

NAME = "テストテスト"  # as many UTF-16 units as "ユメノストラ", so style runs stay valid


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
    variants = {
        "s1_control": (False, False, False),
        "s2_string": (True, False, False),
        "s3_canvas": (False, True, False),
        "s4_both": (True, True, False),
        "s5_no_render": (True, True, True),
    }
    for name, (string, canvas, clear) in variants.items():
        editor = ClipEditor(args.template)
        editor.renew_ids()
        rows = editor.db.execute(
            "SELECT MainId, TextLayerString FROM Layer WHERE ComicStoryInfoType = 1").fetchall()
        if string:
            for layer_id, text in rows:
                new = bytes(text).decode("utf-8").split(" ")[-1].replace("3話", "4話")
                editor.db.execute("UPDATE Layer SET TextLayerString = ? WHERE MainId = ?",
                                  (f"{NAME} {new}".encode("utf-8"), layer_id))
        if canvas:
            editor.db.execute("UPDATE Canvas SET ComicStoryStoryName = ?, ComicStoryStoryIndex = 4", (NAME,))
        if clear:
            for (layer_id,) in editor.db.execute("SELECT MainId FROM Layer WHERE ComicStoryInfoType != 0").fetchall():
                editor.set_layer_image(layer_id, Image.new("RGBA", (1, 1), (0, 0, 0, 0)))
        path = editor.save(out_dir / f"{name}.clip")
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
