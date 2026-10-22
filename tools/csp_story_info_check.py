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
     - s8_inplace.clip  s1, then the live text bytes patched in place (no SQLite rewrite)
     - s9_vacuum.clip   s4, then VACUUM (no stale copy of the old text left in the file)
     - s10_remnant.clip s1, then only the stale copy of the text patched to "ゴミゴミゴミ 9話"

     s1-s5 all still showed the template's "… 3話"; the only other copy of that
     text in those files is a stale one inside a SQLite page, so s8-s10 tell
     whether CSP shows the live row, the stale bytes, or something outside the file.

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
JUNK = "ゴミゴミゴミ"  # same UTF-8 length as NAME, for in-place patches


def _story_rows(editor: ClipEditor) -> list[tuple[int, bytes]]:
    return [(layer_id, bytes(text)) for layer_id, text in editor.db.execute(
        "SELECT MainId, TextLayerString FROM Layer WHERE ComicStoryInfoType = 1").fetchall()]


def _offsets(raw: bytes, key: bytes) -> list[int]:
    found, start = [], 0
    while (index := raw.find(key, start)) != -1:
        found.append(index)
        start = index + 1
    return found


def _live_text(path: Path, layer_id: int) -> bytes:
    return bytes(ClipEditor(path).db.execute(
        "SELECT TextLayerString FROM Layer WHERE MainId = ?", (layer_id,)).fetchone()[0])


def _patched(template: str, out: Path, live: bool, stale: bool) -> Path:
    """Copy the template with new ids, then patch the story text bytes in the file itself."""
    editor = ClipEditor(template)
    editor.renew_ids()
    (layer_id, text), *_ = _story_rows(editor)
    path = editor.save(out)
    raw = bytearray(path.read_bytes())
    old_name = text.decode("utf-8").split(" ")[0].encode("utf-8")
    new_text = text.replace(old_name, NAME.encode("utf-8")).replace("3話".encode(), "4話".encode())
    junk = text.replace(old_name, JUNK.encode("utf-8")).replace("3話".encode(), "9話".encode())
    assert len(new_text) == len(text) == len(junk), "names must have the same UTF-8 length"
    for offset in _offsets(bytes(raw), text):
        probe = bytearray(raw)
        probe[offset:offset + len(text)] = junk
        out.write_bytes(probe)
        is_live = _live_text(out, layer_id) == junk
        if is_live and live:
            raw[offset:offset + len(text)] = new_text
        if not is_live and stale:
            raw[offset:offset + len(text)] = junk
    if live:  # the Canvas row's story name too ("ユメノストラ" followed by its record bytes)
        for offset in _offsets(bytes(raw), old_name):
            if raw[offset:offset + len(text)] != new_text:
                raw[offset:offset + len(old_name)] = NAME.encode("utf-8")
    out.write_bytes(raw)
    print(f"Wrote {out} (live text: {_live_text(out, layer_id).decode('utf-8')})")
    return out


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
        "s9_vacuum": (True, True, False),
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
        if name == "s9_vacuum":
            editor.db.commit()
            editor.db.execute("VACUUM")
        path = editor.save(out_dir / f"{name}.clip")
        print(f"Wrote {path}")
    _patched(args.template, out_dir / "s8_inplace.clip", live=True, stale=False)
    _patched(args.template, out_dir / "s10_remnant.clip", live=False, stale=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
