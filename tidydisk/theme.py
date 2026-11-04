"""Motyw wygladu 'TidyDisk' (ciemny, zielono-turkusowy akcent) albo systemowy (KDE)."""
from __future__ import annotations

THEMES = (("fedora", "TidyDisk (ciemny)"), ("modern", "Nowoczesny (ciemny)"),
          ("modern-light", "Nowoczesny (jasny)"), ("system", "Systemowy (KDE)"))
# paleta Qt dla nowych stylow: okno, tlo pol, tlo przyciskow, tekst, akcent, tekst na akcencie, wyciszony
MODERN = {"modern": ("#0f1216", "#171b21", "#1d222a", "#e8ebf0", "#3ddbb9", "#04201a", "#9aa5b4"),
          "modern-light": ("#f4f6f8", "#ffffff", "#f0f2f5", "#171a20", "#0a7a63", "#ffffff", "#566070")}
BG, PANEL, PANEL2, BORDER = "#14161a", "#1c1f25", "#232830", "#2c323b"
TEXT, MUTED, ACCENT = "#e6e9ee", "#8b93a0", "#2ec4a6"

QSS_FEDORA = f"""
QWidget {{ font-size: 10pt; }}
QMainWindow, QStackedWidget {{ background: {BG}; }}
#nav {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}
#nav::item {{ color: {MUTED}; }}
#nav::item:selected {{ background: rgba(46,196,166,36); color: {TEXT}; border-left: 3px solid {ACCENT}; }}
#nav::item:hover {{ background: rgba(255,255,255,14); }}
#card, #details, #footer, #panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; }}
#footer {{ border-radius: 14px; }}
QTreeWidget {{ background: transparent; alternate-background-color: rgba(255,255,255,6); border: none; }}
QTreeWidget::item {{ padding: 6px 4px; }}
QTreeWidget::item:selected {{ background: rgba(46,196,166,40); color: {TEXT}; }}
QHeaderView::section {{ background: transparent; color: {MUTED}; border: none; padding: 6px 4px; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 7px 14px; border-radius: 8px; margin-right: 4px; }}
QTabBar::tab:selected {{ background: {PANEL2}; color: {TEXT}; }}
QPushButton {{ background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 9px; padding: 7px 14px; color: {TEXT}; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {MUTED}; }}
QPushButton#primary {{ background: {ACCENT}; color: #07231d; border: none; }}
QPushButton#primary:hover {{ background: #3fd9ba; }}
QPushButton#danger {{ background: {ACCENT}; color: #07231d; border: none; }}
QLineEdit, QComboBox, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{ background: {PANEL}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 6px 8px; color: {TEXT}; }}
QProgressBar#meter {{ background: {PANEL2}; }}
QProgressBar#meter::chunk {{ background: {ACCENT}; }}
QProgressBar#meter[level="warn"]::chunk {{ background: #e5a50a; }}
QProgressBar#meter[level="crit"]::chunk {{ background: #d9453f; }}
QLabel#tile {{ background: {PANEL2}; border-radius: 10px; padding: 10px 12px; }}
QLabel#verdict {{ background: rgba(46,196,166,22); border: 1px solid rgba(46,196,166,110); border-radius: 12px; padding: 10px 12px; }}
QLabel#section {{ color: {MUTED}; font-size: 9pt; }}
QLabel#path {{ color: {MUTED}; font-family: monospace; font-size: 9pt; }}
QScrollArea {{ border: none; background: transparent; }}
"""


_ORIG: list = []  # [nazwa stylu, paleta] sprzed pierwszego zastosowania motywu


def apply(app, name: str, base_qss: str) -> None:
    """Ustawia motyw: 'fedora' = styl Fusion + ciemna paleta + QSS, 'system' = bez zmian (tylko podstawowy QSS)."""
    from PyQt6.QtGui import QColor, QPalette
    if not _ORIG:
        _ORIG.extend([app.style().objectName(), QPalette(app.palette())])
    if name not in ("fedora", *MODERN):  # wracamy do stylu i palety systemu (bez restartu)
        app.setStyle(_ORIG[0])
        app.setPalette(_ORIG[1])
        app.setStyleSheet(base_qss)
        return
    app.setStyle("Fusion")
    pal = QPalette()
    c = QColor
    if name in MODERN:
        from . import theme_modern
        bg, base, btn, fg, acc, onacc, muted = MODERN[name]
        R = QPalette.ColorRole
        for role, col in ((R.Window, bg), (R.Base, base), (R.AlternateBase, btn), (R.Button, btn), (R.WindowText, fg),
                          (R.Text, fg), (R.ButtonText, fg), (R.ToolTipBase, btn), (R.ToolTipText, fg),
                          (R.Highlight, acc), (R.HighlightedText, onacc), (R.PlaceholderText, muted)):
            pal.setColor(role, c(col))
        app.setPalette(pal)
        app.setStyleSheet(base_qss + (theme_modern.DARK if name == "modern" else theme_modern.LIGHT))
        return
    for role, col in ((QPalette.ColorRole.Window, BG), (QPalette.ColorRole.Base, PANEL),
                      (QPalette.ColorRole.AlternateBase, PANEL2), (QPalette.ColorRole.Button, PANEL2),
                      (QPalette.ColorRole.WindowText, TEXT), (QPalette.ColorRole.Text, TEXT),
                      (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.ToolTipBase, PANEL2),
                      (QPalette.ColorRole.ToolTipText, TEXT), (QPalette.ColorRole.Highlight, ACCENT),
                      (QPalette.ColorRole.HighlightedText, "#07231d"), (QPalette.ColorRole.PlaceholderText, MUTED)):
        pal.setColor(role, c(col))
    app.setPalette(pal)
    app.setStyleSheet(base_qss + QSS_FEDORA)
