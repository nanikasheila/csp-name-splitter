"""GUI tab: split a name sheet .clip into page .clip files and a .cmc work.

Why: Stage 5 of the rebuild puts the .clip/.cmc split (``split`` command)
     into the GUI, so the whole flow works without a terminal.
How: :class:`CspSplitController` holds the tab's logic and only touches
     controls through ``.value`` / ``.disabled``, so it can be tested with
     plain objects. The plan is checked first (preview image with page
     numbers), then the pages are written in a background thread with
     progress and cancel. The Flet layout is built by :func:`build_csp_tab`.
"""
from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
import io
from pathlib import Path
import threading
from typing import Any

from name_splitter.csp import CspFormatError
from name_splitter.csp.plan_report import render_plan_preview
from name_splitter.csp.split_job import PreparedSplit, SplitOptions, find_cmc_template, prepare_split, run_split

FIT_LABELS = {"basic": "基本枠に合わせる", "trim": "仕上がり枠に合わせる", "cell": "ページ枠全体を収める"}
ORDER_LABELS = {"rtl_ttb": "右→左（右綴じ）", "ltr_ttb": "左→右（左綴じ）"}
PREVIEW_MAX = 1600


@dataclass
class CspSplitFields:
    """Controls of the CSP split tab (any objects with ``.value`` work)."""

    sheet_field: Any
    template_field: Any
    out_dir_field: Any
    make_work_field: Any
    work_name_field: Any
    cmc_template_field: Any
    story_index_field: Any
    fit_field: Any
    order_field: Any
    first_page_field: Any
    plan_btn: Any
    run_btn: Any
    cancel_btn: Any
    summary_text: Any


class CspSplitController:
    """Logic of the CSP split tab.

    ``ui`` must provide ``add_log``, ``set_status``, ``set_progress``,
    ``flush``, ``flush_from_thread`` and ``set_preview_png`` (see
    :class:`name_splitter.app.gui_handlers.GuiHandlers`); ``run_thread``
    starts a background job (Flet's ``page.run_thread``).
    """

    def __init__(self, fields: CspSplitFields, ui: Any,
                 run_thread: Callable[[Callable[[], None]], Any] | None = None) -> None:
        self.f = fields
        self.ui = ui
        self.run_thread = run_thread or (lambda job: threading.Thread(target=job, daemon=True).start())
        self._cancel = threading.Event()

    # --- inputs ---------------------------------------------------------------
    def options(self) -> SplitOptions:
        """Read the fields into split options (raises ValueError when invalid)."""
        sheet = _path(self.f.sheet_field, "ネーム用紙の .clip")
        template = _path(self.f.template_field, "空ページの .clip（テンプレート）")
        out_dir = _path(self.f.out_dir_field, "出力フォルダー")
        make_work = bool(self.f.make_work_field.value)
        cmc_template_text = (self.f.cmc_template_field.value or "").strip()
        return SplitOptions(
            sheet=sheet, template=template, out_dir=out_dir,
            cmc_name=(self.f.work_name_field.value or "").strip() or sheet.stem if make_work else None,
            cmc_template=Path(cmc_template_text) if make_work and cmc_template_text else None,
            fit=self.f.fit_field.value or "basic",
            order=self.f.order_field.value or "rtl_ttb",
            first_page=_int(self.f.first_page_field, "最初のページ番号", default=1),
            story_index=_int(self.f.story_index_field, "話数", default=None),
        )

    def on_sheet_change(self, _: Any = None) -> None:
        """Fill in the .cmc template, work name and output folder from the sheet."""
        text = (self.f.sheet_field.value or "").strip()
        if not text:
            return
        sheet = Path(text)
        if not (self.f.cmc_template_field.value or "").strip():
            found = find_cmc_template(sheet)
            if found is not None:
                self.f.cmc_template_field.value = str(found)
        if not (self.f.work_name_field.value or "").strip():
            self.f.work_name_field.value = sheet.parent.name or sheet.stem
        if not (self.f.out_dir_field.value or "").strip():
            name = (self.f.work_name_field.value or sheet.stem).strip()
            self.f.out_dir_field.value = str(sheet.parent.parent / f"{name}_ページ")
        self.ui.flush()

    # --- plan -----------------------------------------------------------------
    def on_plan(self, _: Any = None) -> None:
        """Check the inputs and show the plan (nothing is written)."""
        prepared = self._prepare()
        if prepared is None:
            return
        plan = prepared.plan
        with_content = [page.number for page in plan.pages if page.contents]
        summary = (f"{len(plan.pages)} ページ（中身あり {len(with_content)}）、"
                   f"倍率 {plan.pages[0].transform.scale:.2f}" if plan.pages else "ページ枠が見つかりません")
        self.f.summary_text.value = summary
        self.ui.add_log(f"[CSP] 計画: {summary}")
        for warning in plan.warnings:
            self.ui.add_log(f"[CSP] 注意: {warning}")
        image = render_plan_preview(plan, prepared.sheet)
        image.thumbnail((PREVIEW_MAX, PREVIEW_MAX))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        self.ui.set_preview_png(buffer.getvalue())
        self.ui.set_status("CSP: 計画を表示しました")
        self.ui.flush()

    # --- run ------------------------------------------------------------------
    def on_run(self, _: Any = None) -> None:
        """Write the pages (and the work) in the background."""
        prepared = self._prepare()
        if prepared is None:
            return
        self._cancel.clear()
        self._set_running(True)
        self.ui.set_progress(0, 1)
        self.ui.add_log(f"[CSP] 書き出し開始: {prepared.options.out_dir}")
        self.ui.flush()
        self.run_thread(lambda: self._run(prepared))

    def on_cancel(self, _: Any = None) -> None:
        self._cancel.set()
        self.ui.set_status("CSP: 中止しています…")
        self.ui.flush()

    def _run(self, prepared: PreparedSplit) -> None:
        def on_page(done: int, total: int, path: Path) -> None:
            self.ui.set_progress(done, total)
            self.ui.set_status(f"CSP: {done}/{total} {path.name}")
            self.ui.flush_from_thread()

        try:
            result = run_split(prepared, on_page=on_page, cancelled=self._cancel.is_set)
        except (OSError, ValueError) as exc:  # CspFormatError is a ValueError too
            self.ui.add_log(f"[ERROR] CSP: {exc}")
            self.ui.set_status("CSP: 失敗しました")
        else:
            for warning in result.warnings:
                self.ui.add_log(f"[CSP] 注意: {warning}")
            if result.cancelled:
                self.ui.add_log(f"[CSP] 中止しました（{len(result.pages)} ページ書き出し済み）")
                self.ui.set_status("CSP: 中止しました")
            else:
                done = f"{len(result.pages)} ページ" + (f"、作品 {result.cmc.name}" if result.cmc else "")
                self.ui.add_log(f"[CSP] 完了: {done} → {prepared.options.out_dir}")
                self.ui.set_status(f"CSP: 完了（{done}）")
        finally:
            self._set_running(False)
            self.ui.flush_from_thread()
            # flush_from_thread only refreshes the shared status widgets.
            for control in (self.f.run_btn, self.f.plan_btn, self.f.cancel_btn):
                update = getattr(control, "update", None)
                if update is not None:
                    update()

    def _prepare(self) -> PreparedSplit | None:
        try:
            return prepare_split(self.options())
        except FileNotFoundError as exc:
            message = f"ファイルが見つかりません: {exc}"
        except CspFormatError as exc:
            message = f"CSP ファイルを読めません: {exc}"
        except ValueError as exc:
            message = str(exc)
        self.ui.add_log(f"[ERROR] CSP: {message}")
        self.ui.set_status(f"CSP: {message}")
        self.ui.flush()
        return None

    def _set_running(self, running: bool) -> None:
        self.f.run_btn.disabled = running
        self.f.plan_btn.disabled = running
        self.f.cancel_btn.disabled = not running


def _path(field: Any, label: str) -> Path:
    text = (field.value or "").strip().strip('"')
    if not text:
        raise ValueError(f"{label}を指定してください")
    return Path(text)


def _int(field: Any, label: str, default: int | None) -> Any:
    text = (field.value or "").strip()
    if not text:
        return default
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"{label}は整数で指定してください") from exc


# --------------------------------------------------------------------------- #
# Flet layout                                                                   #
# --------------------------------------------------------------------------- #
def build_csp_fields(ft: Any) -> CspSplitFields:
    """Create the controls of the CSP split tab."""
    def text(label: str, hint: str = "", expand: bool = True, width: int | None = None) -> Any:
        return ft.TextField(label=label, hint_text=hint, dense=True, expand=expand, width=width)

    def dropdown(label: str, options: dict[str, str], value: str, width: int) -> Any:
        return ft.Dropdown(label=label, value=value, width=width, dense=True,
                           options=[ft.dropdown.Option(key=key, text=name) for key, name in options.items()])

    return CspSplitFields(
        sheet_field=text("ネーム用紙 (.clip)", "ページ枠を描いたネームの .clip"),
        template_field=text("空ページ (.clip)", "同じ作品の空ページを CSP で保存したもの"),
        out_dir_field=text("出力フォルダー", "入力とは別のフォルダー"),
        make_work_field=ft.Checkbox(label="作品ファイル (.cmc) も作る", value=True),
        work_name_field=text("作品ファイル名", "例: 第4話", expand=False, width=200),
        cmc_template_field=text("作品設定の .cmc", "空欄ならネーム用紙と同じフォルダーの .cmc"),
        story_index_field=text("話数", "空欄なら .cmc のまま", expand=False, width=120),
        fit_field=dropdown("配置", FIT_LABELS, "basic", 220),
        order_field=dropdown("読み順", ORDER_LABELS, "rtl_ttb", 180),
        first_page_field=text("最初のページ番号", expand=False, width=140),
        plan_btn=ft.OutlinedButton("計画を確認", icon=ft.Icons.PREVIEW),
        run_btn=ft.ElevatedButton("書き出す", icon=ft.Icons.PLAY_ARROW),
        cancel_btn=ft.OutlinedButton("中止", icon=ft.Icons.CANCEL, disabled=True),
        summary_text=ft.Text("", size=12),
    )


def build_csp_tab(ft: Any, fields: CspSplitFields, controller: CspSplitController,
                  pickers: dict[str, Callable[..., Any]]) -> Any:
    """Lay out the CSP split tab and connect its events."""
    fields.sheet_field.on_blur = controller.on_sheet_change
    fields.plan_btn.on_click = controller.on_plan
    fields.run_btn.on_click = controller.on_run
    fields.cancel_btn.on_click = controller.on_cancel
    fields.first_page_field.value = fields.first_page_field.value or "1"

    def with_picker(field: Any, key: str, icon: Any) -> Any:
        return ft.Row([field, ft.IconButton(icon=icon, on_click=pickers[key], tooltip="選択")], spacing=4)

    return ft.Container(
        content=ft.Column([
            ft.Text("ネーム用紙からページと作品を作る", weight=ft.FontWeight.BOLD, size=12),
            with_picker(fields.sheet_field, "sheet", ft.Icons.FOLDER_OPEN),
            with_picker(fields.template_field, "template", ft.Icons.FOLDER_OPEN),
            with_picker(fields.out_dir_field, "out_dir", ft.Icons.FOLDER),
            ft.Divider(height=8),
            ft.Row([fields.make_work_field, fields.work_name_field, fields.story_index_field]),
            with_picker(fields.cmc_template_field, "cmc_template", ft.Icons.FOLDER_OPEN),
            ft.Divider(height=8),
            ft.Row([fields.fit_field, fields.order_field, fields.first_page_field]),
            ft.Row([fields.plan_btn, fields.run_btn, fields.cancel_btn], spacing=8),
            fields.summary_text,
            ft.Text("入力ファイルは読むだけで、変更しません。", size=11, italic=True),
        ], spacing=8, scroll=ft.ScrollMode.AUTO),
        padding=ft.Padding(8, 6, 8, 6),
        expand=True,
    )


def preview_src(png: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
