from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO


def setup_logging(
    *,
    log_file: str | Path | None = None,
    log_level: str = "INFO",
    console: bool = True,
) -> logging.Logger:
    """ロギング環境をセットアップ
    
    Args:
        log_file: ログファイルのパス（Noneの場合はファイル出力なし）
        log_level: ログレベル（DEBUG/INFO/WARNING/ERROR）
        console: コンソールにも出力するか
        
    Returns:
        設定済みのロガー
    """
    # ルートロガーを取得
    logger = logging.getLogger("csp_name_splitter")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # 既存のハンドラをクリア
    logger.handlers.clear()
    
    # フォーマッタを作成
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # ファイルハンドラを追加
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # コンソールハンドラを追加
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger


def get_logger() -> logging.Logger:
    """設定済みロガーを取得"""
    return logging.getLogger("csp_name_splitter")


def get_default_log_path(output_dir: str | Path | None = None) -> Path:
    """デフォルトのログファイルパスを生成
    
    Args:
        output_dir: 出力ディレクトリ（Noneの場合はカレントディレクトリ）
        
    Returns:
        ログファイルパス
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"csp_name_splitter_{timestamp}.log"
    
    if output_dir:
        log_dir = Path(output_dir) / "logs"
    else:
        log_dir = Path.cwd() / "logs"
    
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / log_filename


class LogCapture:
    """ログメッセージをキャプチャするハンドラ"""
    
    def __init__(self, max_lines: int = 1000) -> None:
        self.max_lines = max_lines
        self.lines: list[str] = []
        self.handler = logging.StreamHandler(self)
        self.handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%H:%M:%S",
            )
        )
    
    def write(self, message: str) -> None:
        """メッセージを記録"""
        if message.strip():
            self.lines.append(message.rstrip())
            if len(self.lines) > self.max_lines:
                self.lines.pop(0)
    
    def flush(self) -> None:
        """フラッシュ（何もしない）"""
        pass
    
    def get_log(self) -> str:
        """キャプチャしたログを取得"""
        return "\n".join(self.lines)
    
    def clear(self) -> None:
        """ログをクリア"""
        self.lines.clear()
    
    def attach(self, logger: logging.Logger | None = None) -> None:
        """ロガーにハンドラを追加"""
        if logger is None:
            logger = get_logger()
        logger.addHandler(self.handler)
    
    def detach(self, logger: logging.Logger | None = None) -> None:
        """ロガーからハンドラを削除"""
        if logger is None:
            logger = get_logger()
        logger.removeHandler(self.handler)


__all__ = [
    "LogCapture",
    "get_default_log_path",
    "get_logger",
    "setup_logging",
]
