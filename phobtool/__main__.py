"""Point d'entrée : python -m phobtool"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    ap = argparse.ArgumentParser(prog="phobtool", description="PhobGCC Tool")
    ap.add_argument("--demo", action="store_true", help="manette virtuelle (sans adaptateur)")
    ap.add_argument("--screenshot", metavar="PREFIX", help="capture chaque onglet puis quitte (tests)")
    args = ap.parse_args()

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QApplication

    from .gui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("PhobGCC Tool")
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#1e1b2e"))
    pal.setColor(QPalette.WindowText, QColor("#e8e4ff"))
    pal.setColor(QPalette.Base, QColor("#15131f"))
    pal.setColor(QPalette.AlternateBase, QColor("#262238"))
    pal.setColor(QPalette.Text, QColor("#e8e4ff"))
    pal.setColor(QPalette.Button, QColor("#2c2742"))
    pal.setColor(QPalette.ButtonText, QColor("#e8e4ff"))
    pal.setColor(QPalette.Highlight, QColor("#6a5acd"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.Link, QColor("#b9a6ff"))
    pal.setColor(QPalette.ToolTipBase, QColor("#2c2742"))
    pal.setColor(QPalette.ToolTipText, QColor("#e8e4ff"))
    pal.setColor(QPalette.PlaceholderText, QColor("#8a84a8"))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor("#6f6a88"))
    app.setPalette(pal)

    win = MainWindow(demo_pad=args.demo)
    win.show()

    if args.screenshot:
        def shoot(i=0):
            if i >= win.tabs.count():
                app.quit()
                return
            win.tabs.setCurrentIndex(i)
            QTimer.singleShot(1200, lambda: (win.grab().save(f"{args.screenshot}{i}.png"), shoot(i + 1)))
        QTimer.singleShot(1500, shoot)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
