"""Nowy styl 'Nowoczesny' (opcjonalny): QSS wygenerowany z tokenow, ciemny i jasny."""
from __future__ import annotations

DARK = r"""/* TidyDisk v2 - szablon; tokeny w znakach at podmienia gen.py (QSS nie ma zmiennych). */
* { font-size: 10pt; }
QWidget { selection-background-color: rgba(61,219,185,46); selection-color: #e8ebf0; }
QMainWindow, QDialog, QStackedWidget { background: #0f1216; }
QToolTip { background: #262c36; color: #e8ebf0; border: 1px solid #2b323c; border-radius: 6px; padding: 6px 8px; }

/* hierarchia tekstu: 20 / 14 / 10 / 9 pt */
QLabel#pagetitle { font-size: 20pt; font-weight: 700; }
QLabel#bigtext { font-size: 14pt; font-weight: 600; }
QLabel#subtitle, QLabel#muted { color: #9aa5b4; }
QLabel#section { color: #9aa5b4; font-size: 9pt; font-weight: 600; }
QLabel#path { color: #9aa5b4; font-family: monospace; font-size: 9pt; }

/* nawigacja */
QListWidget#nav { background: #171b21; border: none; border-right: 1px solid #2b323c; outline: 0; padding: 8px; }
QListWidget#nav::item { color: #9aa5b4; min-height: 40px; padding: 0 12px; margin: 2px 0; border-radius: 8px; }
QListWidget#nav::item:hover { background: rgba(255,255,255,15); color: #e8ebf0; }
QListWidget#nav::item:selected { background: rgba(61,219,185,46); color: #6ee7cc; font-weight: 600; }
QListWidget#nav:focus::item:selected { border: 2px solid #8ab4ff; }

/* karty */
QFrame#card, QFrame#details, QWidget#panel { background: #171b21; border: 1px solid #2b323c; border-radius: 12px; }
QFrame#footer { background: #1d222a; border: 1px solid #2b323c; border-radius: 12px; }
QLabel#tile { background: #1d222a; border-radius: 8px; padding: 10px 12px; }
QLabel#verdict { background: rgba(196,167,255,30); border: 1px solid #c4a7ff; border-radius: 10px; padding: 10px 12px; }
QLabel#banner { background: rgba(74,222,158,30); border: 1px solid #4ade9e; border-radius: 10px; padding: 10px 14px; }
QLabel#banner[level="warn"] { background: rgba(245,184,61,30); border-color: #f5b83d; }

/* przyciski */
QPushButton { background: #1d222a; color: #e8ebf0; border: 1px solid #657084; border-radius: 8px; padding: 7px 14px; min-height: 20px; }
QPushButton:hover { background: #262c36; border-color: #3ddbb9; }
QPushButton:pressed { background: #171b21; }
QPushButton:focus { border: 2px solid #8ab4ff; padding: 6px 13px; }
QPushButton:disabled { background: transparent; color: #7f8a9a; border-color: #2b323c; }
QPushButton#primary { background: #3ddbb9; color: #04201a; border: 1px solid #3ddbb9; font-weight: 600; padding: 9px 20px; min-width: 160px; }
QPushButton#primary:hover { background: #6ee7cc; border-color: #6ee7cc; }
QPushButton#primary:pressed { background: #2bbf9f; }
QPushButton#primary:focus, QPushButton#danger:focus { border: 2px solid #8ab4ff; padding: 8px 19px; }
QPushButton#primary:disabled { background: #262c36; color: #6b7585; border-color: #2b323c; }
QPushButton#danger { background: #c93a46; color: #ffffff; border: 1px solid #c93a46; font-weight: 600; }
QPushButton#danger:hover { background: #b32f3b; border-color: #b32f3b; }
QPushButton#danger:disabled { background: #262c36; color: #6b7585; border-color: #2b323c; }
QPushButton#ghost { background: transparent; border: 1px solid transparent; color: #6ee7cc; }
QPushButton#ghost:hover { background: rgba(255,255,255,15); }
QPushButton::menu-indicator { subcontrol-position: right center; subcontrol-origin: padding; right: 6px; }

/* pola */
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #171b21; border: 1px solid #657084; border-radius: 8px; padding: 6px 10px; min-height: 20px; }
QLineEdit:hover, QComboBox:hover, QSpinBox:hover { border-color: #9aa5b4; }
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 2px solid #8ab4ff; padding: 5px 9px; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: #262c36; border: 1px solid #2b323c; border-radius: 8px; padding: 4px; outline: 0; selection-background-color: rgba(61,219,185,46); selection-color: #e8ebf0; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator, QTreeView::indicator { width: 16px; height: 16px; border: 1px solid #657084; border-radius: 4px; background: #171b21; }
QCheckBox::indicator:checked, QTreeView::indicator:checked { background: #3ddbb9; border-color: #3ddbb9; }
QCheckBox::indicator:hover, QTreeView::indicator:hover { border-color: #3ddbb9; }

/* listy i drzewa */
QTreeView, QTreeWidget { background: transparent; alternate-background-color: rgba(255,255,255,7); border: 2px solid transparent; border-radius: 8px; outline: 0; }
QTreeView:focus, QTreeWidget:focus { border-color: #8ab4ff; }
QTreeView::item, QTreeWidget::item { min-height: 30px; padding: 0 6px; }
QTreeView::item:hover, QTreeWidget::item:hover { background: rgba(255,255,255,15); }
QTreeView::item:selected, QTreeWidget::item:selected { background: rgba(61,219,185,46); color: #e8ebf0; }
QTreeView::item:selected:!active, QTreeWidget::item:selected:!active { background: rgba(154,165,180,40); color: #e8ebf0; }
QHeaderView::section { background: transparent; color: #9aa5b4; font-weight: 600; font-size: 9pt; border: none; border-bottom: 1px solid #2b323c; padding: 8px 6px; }

/* zakladki */
QTabBar { background: transparent; }
QTabBar::tab { background: transparent; color: #9aa5b4; padding: 7px 16px; margin-right: 4px; border-radius: 8px; }
QTabBar::tab:hover { background: rgba(255,255,255,15); color: #e8ebf0; }
QTabBar::tab:selected { background: rgba(61,219,185,46); color: #6ee7cc; font-weight: 600; }

/* postep */
QProgressBar { background: #262c36; border: none; border-radius: 4px; color: #e8ebf0; text-align: center; }
QProgressBar::chunk { background: #3ddbb9; border-radius: 4px; }
QProgressBar#busy { border-radius: 3px; }
QProgressBar#busy::chunk { border-radius: 3px; }
QProgressBar#meter { max-height: 8px; }
QProgressBar#meter[level="warn"]::chunk { background: #f5b83d; }
QProgressBar#meter[level="crit"]::chunk { background: #c93a46; }

/* plakietki ocen: setProperty("rating", "safe|review|mine|keep") na QLabel#badge */
QLabel#badge { border-radius: 9px; padding: 2px 10px; font-size: 9pt; font-weight: 600; border: 1px solid transparent; }
QLabel#badge[rating="safe"] { background: rgba(74,222,158,30); color: #4ade9e; border-color: #4ade9e; }
QLabel#badge[rating="review"] { background: rgba(245,184,61,30); color: #f5b83d; border-color: #f5b83d; }
QLabel#badge[rating="mine"] { background: rgba(106,174,255,30); color: #6aaeff; border-color: #6aaeff; }
QLabel#badge[rating="keep"] { background: rgba(255,138,152,30); color: #ff8a98; border-color: #ff8a98; }
QLabel#aibadge { background: rgba(196,167,255,30); color: #c4a7ff; border: 1px solid #c4a7ff; border-radius: 9px; padding: 2px 10px; font-size: 9pt; font-weight: 600; }

/* paski przewijania, menu, pasek stanu */
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: #657084; border-radius: 4px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: #9aa5b4; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: #657084; border-radius: 4px; min-width: 32px; }
QScrollBar::handle:horizontal:hover { background: #9aa5b4; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QMenu { background: #262c36; border: 1px solid #2b323c; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 7px 24px 7px 14px; border-radius: 6px; }
QMenu::item:selected { background: rgba(61,219,185,46); }
QMenu::item:disabled { color: #6b7585; }
QMenu::separator { height: 1px; background: #2b323c; margin: 5px 8px; }
QStatusBar { background: #171b21; border-top: 1px solid #2b323c; color: #9aa5b4; }
QStatusBar::item { border: none; }
QSplitter::handle { background: transparent; }
"""

LIGHT = r"""/* TidyDisk v2 - szablon; tokeny w znakach at podmienia gen.py (QSS nie ma zmiennych). */
* { font-size: 10pt; }
QWidget { selection-background-color: rgba(10,122,99,34); selection-color: #171a20; }
QMainWindow, QDialog, QStackedWidget { background: #f4f6f8; }
QToolTip { background: #e6e9ee; color: #171a20; border: 1px solid #d5dae2; border-radius: 6px; padding: 6px 8px; }

/* hierarchia tekstu: 20 / 14 / 10 / 9 pt */
QLabel#pagetitle { font-size: 20pt; font-weight: 700; }
QLabel#bigtext { font-size: 14pt; font-weight: 600; }
QLabel#subtitle, QLabel#muted { color: #566070; }
QLabel#section { color: #566070; font-size: 9pt; font-weight: 600; }
QLabel#path { color: #566070; font-family: monospace; font-size: 9pt; }

/* nawigacja */
QListWidget#nav { background: #ffffff; border: none; border-right: 1px solid #d5dae2; outline: 0; padding: 8px; }
QListWidget#nav::item { color: #566070; min-height: 40px; padding: 0 12px; margin: 2px 0; border-radius: 8px; }
QListWidget#nav::item:hover { background: rgba(0,0,0,12); color: #171a20; }
QListWidget#nav::item:selected { background: rgba(10,122,99,34); color: #0a6a56; font-weight: 600; }
QListWidget#nav:focus::item:selected { border: 2px solid #1558c0; }

/* karty */
QFrame#card, QFrame#details, QWidget#panel { background: #ffffff; border: 1px solid #d5dae2; border-radius: 12px; }
QFrame#footer { background: #f0f2f5; border: 1px solid #d5dae2; border-radius: 12px; }
QLabel#tile { background: #f0f2f5; border-radius: 8px; padding: 10px 12px; }
QLabel#verdict { background: rgba(107,63,196,24); border: 1px solid #6b3fc4; border-radius: 10px; padding: 10px 12px; }
QLabel#banner { background: rgba(10,111,68,28); border: 1px solid #0a6f44; border-radius: 10px; padding: 10px 14px; }
QLabel#banner[level="warn"] { background: rgba(138,90,0,28); border-color: #8a5a00; }

/* przyciski */
QPushButton { background: #f0f2f5; color: #171a20; border: 1px solid #7d8797; border-radius: 8px; padding: 7px 14px; min-height: 20px; }
QPushButton:hover { background: #e6e9ee; border-color: #0a7a63; }
QPushButton:pressed { background: #ffffff; }
QPushButton:focus { border: 2px solid #1558c0; padding: 6px 13px; }
QPushButton:disabled { background: transparent; color: #6f7a8a; border-color: #d5dae2; }
QPushButton#primary { background: #0a7a63; color: #ffffff; border: 1px solid #0a7a63; font-weight: 600; padding: 9px 20px; min-width: 160px; }
QPushButton#primary:hover { background: #096a56; border-color: #096a56; }
QPushButton#primary:pressed { background: #08594a; }
QPushButton#primary:focus, QPushButton#danger:focus { border: 2px solid #1558c0; padding: 8px 19px; }
QPushButton#primary:disabled { background: #e6e9ee; color: #8c96a5; border-color: #d5dae2; }
QPushButton#danger { background: #c0283a; color: #ffffff; border: 1px solid #c0283a; font-weight: 600; }
QPushButton#danger:hover { background: #a82032; border-color: #a82032; }
QPushButton#danger:disabled { background: #e6e9ee; color: #8c96a5; border-color: #d5dae2; }
QPushButton#ghost { background: transparent; border: 1px solid transparent; color: #0a6a56; }
QPushButton#ghost:hover { background: rgba(0,0,0,12); }
QPushButton::menu-indicator { subcontrol-position: right center; subcontrol-origin: padding; right: 6px; }

/* pola */
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #ffffff; border: 1px solid #7d8797; border-radius: 8px; padding: 6px 10px; min-height: 20px; }
QLineEdit:hover, QComboBox:hover, QSpinBox:hover { border-color: #566070; }
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border: 2px solid #1558c0; padding: 5px 9px; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: #e6e9ee; border: 1px solid #d5dae2; border-radius: 8px; padding: 4px; outline: 0; selection-background-color: rgba(10,122,99,34); selection-color: #171a20; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator, QTreeView::indicator { width: 16px; height: 16px; border: 1px solid #7d8797; border-radius: 4px; background: #ffffff; }
QCheckBox::indicator:checked, QTreeView::indicator:checked { background: #0a7a63; border-color: #0a7a63; }
QCheckBox::indicator:hover, QTreeView::indicator:hover { border-color: #0a7a63; }

/* listy i drzewa */
QTreeView, QTreeWidget { background: transparent; alternate-background-color: rgba(0,0,0,6); border: 2px solid transparent; border-radius: 8px; outline: 0; }
QTreeView:focus, QTreeWidget:focus { border-color: #1558c0; }
QTreeView::item, QTreeWidget::item { min-height: 30px; padding: 0 6px; }
QTreeView::item:hover, QTreeWidget::item:hover { background: rgba(0,0,0,12); }
QTreeView::item:selected, QTreeWidget::item:selected { background: rgba(10,122,99,34); color: #171a20; }
QTreeView::item:selected:!active, QTreeWidget::item:selected:!active { background: rgba(86,96,112,40); color: #171a20; }
QHeaderView::section { background: transparent; color: #566070; font-weight: 600; font-size: 9pt; border: none; border-bottom: 1px solid #d5dae2; padding: 8px 6px; }

/* zakladki */
QTabBar { background: transparent; }
QTabBar::tab { background: transparent; color: #566070; padding: 7px 16px; margin-right: 4px; border-radius: 8px; }
QTabBar::tab:hover { background: rgba(0,0,0,12); color: #171a20; }
QTabBar::tab:selected { background: rgba(10,122,99,34); color: #0a6a56; font-weight: 600; }

/* postep */
QProgressBar { background: #e6e9ee; border: none; border-radius: 4px; color: #171a20; text-align: center; }
QProgressBar::chunk { background: #0a7a63; border-radius: 4px; }
QProgressBar#busy { border-radius: 3px; }
QProgressBar#busy::chunk { border-radius: 3px; }
QProgressBar#meter { max-height: 8px; }
QProgressBar#meter[level="warn"]::chunk { background: #8a5a00; }
QProgressBar#meter[level="crit"]::chunk { background: #c0283a; }

/* plakietki ocen: setProperty("rating", "safe|review|mine|keep") na QLabel#badge */
QLabel#badge { border-radius: 9px; padding: 2px 10px; font-size: 9pt; font-weight: 600; border: 1px solid transparent; }
QLabel#badge[rating="safe"] { background: rgba(10,111,68,28); color: #0a6f44; border-color: #0a6f44; }
QLabel#badge[rating="review"] { background: rgba(138,90,0,28); color: #8a5a00; border-color: #8a5a00; }
QLabel#badge[rating="mine"] { background: rgba(21,88,192,26); color: #1558c0; border-color: #1558c0; }
QLabel#badge[rating="keep"] { background: rgba(179,38,58,24); color: #b3263a; border-color: #b3263a; }
QLabel#aibadge { background: rgba(107,63,196,24); color: #6b3fc4; border: 1px solid #6b3fc4; border-radius: 9px; padding: 2px 10px; font-size: 9pt; font-weight: 600; }

/* paski przewijania, menu, pasek stanu */
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: #7d8797; border-radius: 4px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: #566070; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: #7d8797; border-radius: 4px; min-width: 32px; }
QScrollBar::handle:horizontal:hover { background: #566070; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QMenu { background: #e6e9ee; border: 1px solid #d5dae2; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 7px 24px 7px 14px; border-radius: 6px; }
QMenu::item:selected { background: rgba(10,122,99,34); }
QMenu::item:disabled { color: #8c96a5; }
QMenu::separator { height: 1px; background: #d5dae2; margin: 5px 8px; }
QStatusBar { background: #ffffff; border-top: 1px solid #d5dae2; color: #566070; }
QStatusBar::item { border: none; }
QSplitter::handle { background: transparent; }
"""
