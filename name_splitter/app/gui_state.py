"""GUI state management for CSP Name Splitter.

集中管理された状態クラスにより、状態の散在を防ぎ、
変更の追跡とデバッグを容易にします。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from name_splitter.core import CancelToken


@dataclass
class PageSizeCache:
    """ページサイズのキャッシュ（Custom選択時のフォールバック用）。"""
    width: int = 0
    height: int = 0
    
    def update(self, width: int, height: int) -> None:
        """キャッシュを更新。"""
        self.width = width
        self.height = height
    
    def get(self) -> tuple[int, int]:
        """キャッシュされた値を取得。"""
        return self.width, self.height


@dataclass
class UnitState:
    """単位変換の現在状態（px ↔ mm 変換時に使用）。"""
    margin_unit: str = "px"
    page_size_unit: str = "px"
    gutter_unit: str = "px"


@dataclass
class PreviewImageCache:
    """リサイズ済みプレビュー画像のキャッシュ。

    Why: build_preview_png は毎回ディスクから画像を読み込み RGBA 変換と
         リサイズを行う。グリッド設定変更だけでフルパイプラインが走るのは
         無駄であり、プレビュー体感速度の最大ボトルネック。
    How: ファイルパス + max_dim + ファイル更新時刻をキーとして PIL Image
         (RGBA, リサイズ済み) を保持。キーが一致すればキャッシュを返す。
    """
    _path: str = ""
    _max_dim: int = 0
    _mtime: float = 0.0
    _image: Any = None   # PIL.Image.Image | None
    _scale: float = 1.0

    def get(
        self, path: str, max_dim: int
    ) -> tuple[Any, float] | None:
        """Retrieve cached image if path/max_dim/mtime all match.

        Why: Avoids redundant disk I/O + RGBA conversion + resize when
             only the grid overlay needs to change.
        How: Compares stored key fields. On mtime mismatch (file was
             edited externally) the cache is invalidated.

        Returns:
            (PIL.Image.Image copy, scale) or None on miss.
        """
        if path != self._path or max_dim != self._max_dim:
            return None
        try:
            current_mtime = Path(path).stat().st_mtime
        except OSError:
            return None
        if current_mtime != self._mtime:
            return None
        if self._image is None:
            return None
        return self._image.copy(), self._scale

    def store(
        self, path: str, max_dim: int, image: Any, scale: float
    ) -> None:
        """Store a freshly loaded/resized image in the cache.

        Why: Called once after a cache miss so subsequent preview builds
             skip the expensive read+resize pipeline.
        How: Records the key fields and a copy of the PIL Image.
        """
        try:
            mtime = Path(path).stat().st_mtime
        except OSError:
            mtime = 0.0
        self._path = path
        self._max_dim = max_dim
        self._mtime = mtime
        self._image = image.copy()
        self._scale = scale


@dataclass
class GuiState:
    """GUIアプリケーションの状態を一元管理するクラス。
    
    辞書ベースの状態管理から脱却し、型安全で明示的な
    状態管理を実現します。
    
    Attributes:
        cancel_token: ジョブのキャンセルトークン
        unit_state: 単位変換の現在状態
        active_tab_index: アクティブなタブ（0=Image Split, 1=Template）
        auto_preview_enabled: 自動プレビューの有効/無効
        page_size_cache: ページサイズのキャッシュ
    """
    cancel_token: CancelToken = field(default_factory=CancelToken)
    unit_state: UnitState = field(default_factory=UnitState)
    active_tab_index: int = 0
    auto_preview_enabled: bool = False
    page_size_cache: PageSizeCache = field(default_factory=PageSizeCache)
    preview_image_cache: PreviewImageCache = field(default_factory=PreviewImageCache)
    
    def reset_cancel_token(self) -> None:
        """新しいキャンセルトークンを作成（ジョブ開始時に使用）。"""
        self.cancel_token = CancelToken()
    
    def request_cancel(self) -> None:
        """現在のジョブのキャンセルをリクエスト。"""
        self.cancel_token.cancel()
    
    def is_image_split_tab(self) -> bool:
        """Image Splitタブがアクティブか判定。"""
        return self.active_tab_index == 0
    
    def is_template_tab(self) -> bool:
        """Templateタブがアクティブか判定。"""
        return self.active_tab_index == 1
    
    def set_tab(self, index: int) -> None:
        """アクティブなタブを設定。"""
        self.active_tab_index = index
    
    def enable_auto_preview(self) -> None:
        """自動プレビューを有効化（初期化完了後に呼ぶ）。"""
        self.auto_preview_enabled = True
    
    def disable_auto_preview(self) -> None:
        """自動プレビューを無効化（設定反映中など）。"""
        self.auto_preview_enabled = False


__all__ = ["GuiState", "UnitState", "PageSizeCache", "PreviewImageCache"]
