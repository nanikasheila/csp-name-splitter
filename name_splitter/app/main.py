"""Standalone entry point for packaged distribution.

Why: flet pack / PyInstaller は __main__.py ではなく明示的な main.py を要求する。
How: gui.main() を呼び出すだけのシンプルなラッパー。
"""
from name_splitter.app.gui import main

if __name__ == "__main__":
    main()
