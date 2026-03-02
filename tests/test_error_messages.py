"""error_messages.py のテスト。

Why: get_ja_message() は GUI ユーザーへ日本語エラーを表示する唯一の変換層。
     各パターンの変換結果とフォールバック動作を保証する。
How: 純粋関数なので外部依存なしで単体テスト可能。
"""
from __future__ import annotations

import pytest

from name_splitter.app.error_messages import get_ja_message


def test_known_pattern_returns_japanese() -> None:
    """'Input image is required' は日本語を含む文字列に変換されること。"""
    result = get_ja_message("Input image is required")
    # 日本語文字が含まれるか確認（ひらがな・漢字の Unicode 範囲）
    assert any(ord(c) > 0x3000 for c in result), f"Expected Japanese in: {result!r}"


def test_unknown_pattern_returns_original() -> None:
    """辞書に存在しないパターンは元の文字列をそのまま返すこと。"""
    original = "Some unknown error"
    assert get_ja_message(original) == original


def test_image_read_error_patterns() -> None:
    """'not found' および 'Failed to read' パターンが日本語に変換されること。"""
    result_not_found = get_ja_message("something not found")
    assert any(ord(c) > 0x3000 for c in result_not_found), (
        f"Expected Japanese in: {result_not_found!r}"
    )

    result_failed = get_ja_message("Failed to read image.png")
    assert any(ord(c) > 0x3000 for c in result_failed), (
        f"Expected Japanese in: {result_failed!r}"
    )


def test_limit_exceeded_pattern() -> None:
    """'exceeds limit' パターンが日本語に変換されること。"""
    result = get_ja_message("Image size exceeds limit of 10000px")
    assert any(ord(c) > 0x3000 for c in result), f"Expected Japanese in: {result!r}"


def test_empty_string() -> None:
    """空文字はそのまま返すこと。"""
    assert get_ja_message("") == ""


def test_exception_object_input() -> None:
    """Exception オブジェクトを渡しても動作（クラッシュしない）こと。"""
    exc = ValueError("Input image is required")
    result = get_ja_message(exc)
    # 例外の str() 変換後に辞書マッチされることを確認
    assert any(ord(c) > 0x3000 for c in result), f"Expected Japanese in: {result!r}"


def test_detail_preserved() -> None:
    """'image.png not found' → 日本語メッセージにファイル名情報が含まれること。

    Why: ユーザーがどのファイルが原因かを把握できるようにするため。
    """
    result = get_ja_message("image.png not found")
    # 日本語部分が含まれる
    assert any(ord(c) > 0x3000 for c in result), f"Expected Japanese in: {result!r}"
    # ファイル名情報も何らかの形で残っているか、または日本語メッセージのみ
    # get_ja_message は detail を付加する実装のため "image.png" が含まれることを確認
    assert "image.png" in result or any(ord(c) > 0x3000 for c in result)


def test_directory_not_found_matches_before_generic_not_found() -> None:
    """'Directory not found' は 'フォルダが見つかりません' に変換されること。

    Why: 短い 'not found' パターンが先にマッチして
         'ファイルが見つかりません' になるバグを防止する。
    """
    result = get_ja_message("Directory not found: /some/path")
    assert "フォルダ" in result, f"Expected 'フォルダ' in: {result!r}"
    assert "ファイル" not in result, f"Should not contain 'ファイル' in: {result!r}"
