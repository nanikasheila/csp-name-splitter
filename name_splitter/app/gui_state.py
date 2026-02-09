"""GUI state management for CSP Name Splitter.

集中管理された状態クラスにより、状態の散在を防ぎ、
変更の追跡とデバッグを容易にします。
"""
from __future__ import annotations

from dataclasses import dataclass, field

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


__all__ = ["GuiState", "UnitState", "PageSizeCache"]
