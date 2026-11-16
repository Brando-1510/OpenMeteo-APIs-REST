from pathlib import Path


_STYLE_FILE = Path(__file__).with_name("main.qss")

def load_main_stylesheet() -> str:
    return _STYLE_FILE.read_text(encoding="utf-8")