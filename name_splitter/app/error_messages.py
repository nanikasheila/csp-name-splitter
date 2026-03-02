"""GUI向けエラーメッセージ日本語化辞書。

Why: ターゲットユーザー（漫画家）に英語エラーが表示されると理解できない。
How: raiseサイトの英語文字列は維持し、GUI表示時のみ日本語マッピングを適用。
     既存テストのmatch=アサーションへの影響をゼロにする。
"""
from __future__ import annotations

# Why: 長いパターンを先に配置して最長マッチ優先にする。
#      短い "not found" が "Directory not found" より先にヒットするのを防ぐ。
_JA_MESSAGES: list[tuple[str, str]] = [
    ("Input image is required", "入力画像を指定してください"),
    ("No output directory", "出力先フォルダを指定してください"),
    ("Directory not found", "フォルダが見つかりません"),
    ("Failed to open folder", "フォルダを開けませんでした"),
    ("Failed to read", "画像の読み込みに失敗しました"),
    ("not found", "ファイルが見つかりません"),
    ("exceeds limit", "画像サイズが上限を超えています"),
    ("must be between", "値が有効範囲外です"),
    ("Permission denied", "アクセス権がありません"),
    ("No space left", "ディスク容量が不足しています"),
    ("ConfigError", "設定ファイルにエラーがあります"),
    ("ImageReadError", "画像の読み込みに失敗しました"),
    ("LimitExceededError", "サイズ制限を超えています"),
]


def get_ja_message(error: BaseException | str) -> str:
    """Convert error to Japanese message for GUI display.

    Why: raiseサイトの英語文字列はテスト互換性のため変更不可。
    How: リスト（タプル配列）を先頭から順に部分一致で検索し、最初にマッチした日本語を返す。
         長いパターンを先に配置して最長マッチ優先にしている。
         マッチしない場合は元の英語文字列をそのまま返す（フォールバック）。

    Args:
        error: BaseException または文字列メッセージ

    Returns:
        日本語メッセージ文字列。辞書にない場合は元の文字列。
    """
    text = str(error)
    for key, ja in _JA_MESSAGES:
        if key in text:
            # 元のパス情報等を付加
            detail = text.replace(key, "").strip(": ")
            return f"{ja}: {detail}" if detail else ja
    return text


__all__ = ["get_ja_message"]
