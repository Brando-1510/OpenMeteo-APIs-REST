from __future__ import annotations
import sys
from PySide6.QtWidgets import QApplication
from app.styles import load_main_stylesheet
from app.windows.main_window import MainWindow


try:
    import app.resources_rc  # noqa: F401
    
except ModuleNotFoundError as error:
    raise RuntimeError(
        "Falta app/resources_rc.py. Genera los recursos con: "
        "pyside6-rcc app/resources.qrc -o app/resources_rc.py") from error


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Proyecto Clima REST Python")
    app.setStyle("Fusion")
    app.setStyleSheet(load_main_stylesheet())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
