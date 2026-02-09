"""Unit tests for gui_utils module.

疎結合な設計の検証：
- 各関数が純粋関数として動作するか
- 外部状態に依存していないか
- データクラスを使ったインターフェースが明確か
"""
import pytest

from name_splitter.app.gui_utils import (
    parse_int,
    parse_float,
    mm_to_px,
    px_to_mm,
    convert_margin_to_px,
    convert_unit_value,
    PageSizeParams,
    compute_page_size_px,
    compute_canvas_size_px,
    FrameSizeParams,
    compute_frame_size_mm,
    GridConfigParams,
    build_grid_config,
    TemplateStyleParams,
    build_template_style,
)


class TestParsers:
    """パーサー関数のテスト（純粋関数）。"""
    
    def test_parse_int_valid(self):
        assert parse_int("42", "TestField") == 42
        assert parse_int("0", "TestField") == 0
        assert parse_int("-10", "TestField") == -10
    
    def test_parse_int_invalid(self):
        with pytest.raises(ValueError, match="TestField must be an integer"):
            parse_int("abc", "TestField")
        with pytest.raises(ValueError, match="TestField must be an integer"):
            parse_int("3.14", "TestField")
    
    def test_parse_float_valid(self):
        assert parse_float("3.14", "TestField") == pytest.approx(3.14)
        assert parse_float("42", "TestField") == pytest.approx(42.0)
        assert parse_float("-10.5", "TestField") == pytest.approx(-10.5)
    
    def test_parse_float_invalid(self):
        with pytest.raises(ValueError, match="TestField must be a number"):
            parse_float("abc", "TestField")


class TestUnitConversion:
    """単位変換関数のテスト（純粋関数）。"""
    
    def test_mm_to_px_300dpi(self):
        # 25.4mm = 1 inch = 300px @ 300dpi
        assert mm_to_px(25.4, 300) == 300
        assert mm_to_px(0, 300) == 0
        # A4 width @ 300dpi
        assert mm_to_px(210, 300) == 2480
    
    def test_mm_to_px_600dpi(self):
        assert mm_to_px(25.4, 600) == 600
        # A4 width @ 600dpi
        assert mm_to_px(210, 600) == 4961
    
    def test_px_to_mm_300dpi(self):
        assert px_to_mm(300, 300) == pytest.approx(25.4)
        assert px_to_mm(2480, 300) == pytest.approx(210, abs=0.5)
    
    def test_px_to_mm_600dpi(self):
        assert px_to_mm(600, 600) == pytest.approx(25.4)
        assert px_to_mm(4961, 600) == pytest.approx(210, abs=0.5)
    
    def test_px_to_mm_invalid_dpi(self):
        with pytest.raises(ValueError, match="DPI must be positive"):
            px_to_mm(100, 0)
    
    def test_convert_margin_to_px_px_unit(self):
        assert convert_margin_to_px("100", "px", 300) == 100
        assert convert_margin_to_px("0", "px", 300) == 0
    
    def test_convert_margin_to_px_mm_unit(self):
        assert convert_margin_to_px("25.4", "mm", 300) == 300
        assert convert_margin_to_px("10", "mm", 300) == 118
    
    def test_convert_unit_value_px_to_mm(self):
        result = convert_unit_value("300", "px", "mm", 300)
        assert result == "25.40"
    
    def test_convert_unit_value_mm_to_px(self):
        result = convert_unit_value("25.4", "mm", "px", 300)
        assert result == "300"
    
    def test_convert_unit_value_same_unit(self):
        result = convert_unit_value("100", "px", "px", 300)
        assert result == "100"


class TestPageSizeComputation:
    """ページサイズ計算のテスト（純粋関数、データクラス使用）。"""
    
    def test_compute_page_size_px_a4_300dpi(self):
        params = PageSizeParams(
            page_size_name="A4",
            orientation="portrait",
            dpi=300,
        )
        w, h = compute_page_size_px(params)
        assert w == 2480  # A4 width @ 300dpi
        assert h == 3508  # A4 height @ 300dpi
    
    def test_compute_page_size_px_a4_landscape(self):
        params = PageSizeParams(
            page_size_name="A4",
            orientation="landscape",
            dpi=300,
        )
        w, h = compute_page_size_px(params)
        assert w == 3508  # Swapped
        assert h == 2480
    
    def test_compute_page_size_px_custom_px(self):
        params = PageSizeParams(
            page_size_name="Custom",
            orientation="portrait",
            dpi=300,
            custom_width="1000",
            custom_height="2000",
            custom_unit="px",
        )
        w, h = compute_page_size_px(params)
        assert w == 1000
        assert h == 2000
    
    def test_compute_page_size_px_custom_mm(self):
        params = PageSizeParams(
            page_size_name="Custom",
            orientation="portrait",
            dpi=300,
            custom_width="210",
            custom_height="297",
            custom_unit="mm",
        )
        w, h = compute_page_size_px(params)
        assert w == 2480  # 210mm @ 300dpi
        assert h == 3508  # 297mm @ 300dpi
    
    def test_compute_page_size_px_custom_fallback(self):
        # Customだが値が未入力の場合、last_w/last_hを使用
        params = PageSizeParams(
            page_size_name="Custom",
            orientation="portrait",
            dpi=300,
        )
        w, h = compute_page_size_px(params, last_w=1234, last_h=5678)
        assert w == 1234
        assert h == 5678
    
    def test_compute_canvas_size_px(self):
        from name_splitter.core.config import GridConfig
        
        grid = GridConfig(
            rows=2,
            cols=3,
            order="rtl_ttb",
            margin_px=0,
            margin_top_px=10,
            margin_bottom_px=20,
            margin_left_px=30,
            margin_right_px=40,
            gutter_px=5,
            dpi=300,
        )
        page_w, page_h = 100, 200
        
        canvas_w, canvas_h = compute_canvas_size_px(grid, page_w, page_h)
        
        # Width: 30(left) + 40(right) + 3*100(pages) + 2*5(gutters) = 380
        assert canvas_w == 380
        # Height: 10(top) + 20(bottom) + 2*200(pages) + 1*5(gutter) = 435
        assert canvas_h == 435


class TestFrameSizeComputation:
    """フレームサイズ計算のテスト（Template用）。"""
    
    def test_compute_frame_size_mm_use_per_page(self):
        params = FrameSizeParams(
            mode="Use per-page size",
            dpi=300,
            orientation="portrait",
            width_value="",
            height_value="",
            page_width_px=2480,
            page_height_px=3508,
        )
        w, h = compute_frame_size_mm(params)
        assert w == pytest.approx(210, abs=0.5)
        assert h == pytest.approx(297, abs=0.5)
    
    def test_compute_frame_size_mm_a4_preset(self):
        params = FrameSizeParams(
            mode="A4",
            dpi=300,
            orientation="portrait",
            width_value="",
            height_value="",
            page_width_px=0,
            page_height_px=0,
        )
        w, h = compute_frame_size_mm(params)
        assert w == pytest.approx(210, abs=0.5)
        assert h == pytest.approx(297, abs=0.5)
    
    def test_compute_frame_size_mm_custom_px(self):
        params = FrameSizeParams(
            mode="Custom px",
            dpi=300,
            orientation="portrait",
            width_value="1000",
            height_value="2000",
            page_width_px=0,
            page_height_px=0,
        )
        w, h = compute_frame_size_mm(params)
        assert w == pytest.approx(1000 * 25.4 / 300, abs=0.5)
        assert h == pytest.approx(2000 * 25.4 / 300, abs=0.5)
    
    def test_compute_frame_size_mm_custom_mm(self):
        params = FrameSizeParams(
            mode="Custom mm",
            dpi=300,
            orientation="portrait",
            width_value="150",
            height_value="250",
            page_width_px=0,
            page_height_px=0,
        )
        w, h = compute_frame_size_mm(params)
        assert w == 150.0
        assert h == 250.0


class TestGridConfigBuilder:
    """GridConfig構築のテスト。"""
    
    def test_build_grid_config_basic(self):
        params = GridConfigParams(
            rows="4",
            cols="4",
            order="rtl_ttb",
            margin_top="10",
            margin_bottom="20",
            margin_left="30",
            margin_right="40",
            margin_unit="px",
            gutter="5",
            gutter_unit="px",
            dpi="300",
            page_size_name="A4",
            orientation="portrait",
            page_width_px=2480,
            page_height_px=3508,
            page_size_unit="px",
        )
        
        grid = build_grid_config(params)
        
        assert grid.rows == 4
        assert grid.cols == 4
        assert grid.order == "rtl_ttb"
        assert grid.margin_top_px == 10
        assert grid.margin_bottom_px == 20
        assert grid.margin_left_px == 30
        assert grid.margin_right_px == 40
        assert grid.gutter_px == 5
        assert grid.dpi == 300
    
    def test_build_grid_config_mm_unit(self):
        params = GridConfigParams(
            rows="2",
            cols="2",
            order="ltr_ttb",
            margin_top="10",
            margin_bottom="10",
            margin_left="10",
            margin_right="10",
            margin_unit="mm",
            gutter="5",
            gutter_unit="mm",
            dpi="300",
            page_size_name="A4",
            orientation="portrait",
            page_width_px=2480,
            page_height_px=3508,
            page_size_unit="px",
        )
        
        grid = build_grid_config(params)
        
        # 10mm @ 300dpi = 118px
        assert grid.margin_top_px == 118
        assert grid.margin_bottom_px == 118
        assert grid.margin_left_px == 118
        assert grid.margin_right_px == 118
        # 5mm @ 300dpi = 59px
        assert grid.gutter_px == 59


class TestTemplateStyleBuilder:
    """TemplateStyle構築のテスト。"""
    
    def test_build_template_style_basic(self):
        params = TemplateStyleParams(
            grid_color="#FF5030",
            grid_alpha="170",
            grid_width="2",
            finish_color="#FFFFFF",
            finish_alpha="255",
            finish_line_width="3",
            finish_size_mode="Use per-page size",
            finish_width="",
            finish_height="",
            finish_offset_x="0",
            finish_offset_y="0",
            draw_finish=True,
            basic_color="#00AAFF",
            basic_alpha="200",
            basic_line_width="1",
            basic_size_mode="Use per-page size",
            basic_width="",
            basic_height="",
            basic_offset_x="5",
            basic_offset_y="5",
            draw_basic=True,
            dpi=300,
            orientation="portrait",
            page_width_px=2480,
            page_height_px=3508,
        )
        
        style = build_template_style(params)
        
        assert style.grid_width == 2
        assert style.finish_width == 3
        assert style.basic_width == 1
        assert style.draw_finish is True
        assert style.draw_basic is True
        assert style.finish_offset_x_mm == 0.0
        assert style.finish_offset_y_mm == 0.0
        assert style.basic_offset_x_mm == 5.0
        assert style.basic_offset_y_mm == 5.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
