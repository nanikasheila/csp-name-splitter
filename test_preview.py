#!/usr/bin/env python
"""プレビュー機能のテスト"""
from pathlib import Path
from name_splitter.core.preview import build_preview_png
from name_splitter.core.config import GridConfig

# サンプル画像があるか確認
sample_dir = Path("sample/ユメノストラ_002_pages/flat")
sample_images = list(sample_dir.glob("*.png"))

if sample_images:
    sample_image = sample_images[0]
    print(f"Using sample image: {sample_image}")
    
    # 4x4グリッドでプレビューを生成
    grid = GridConfig(rows=4, cols=4, order="rtl_ttb", margin_px=0, gutter_px=0)
    
    print("Generating preview with page numbers...")
    preview_bytes = build_preview_png(
        sample_image, 
        grid,
        show_page_numbers=True
    )
    
    # プレビューを保存
    output_path = Path("test_preview_output.png")
    output_path.write_bytes(preview_bytes)
    print(f"Preview saved to: {output_path}")
    print(f"Preview size: {len(preview_bytes)} bytes")
    print("✓ Preview generation successful!")
else:
    print("No sample images found. Skipping test.")
