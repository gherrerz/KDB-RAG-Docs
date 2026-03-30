"""Shared UI theme tokens and stylesheet for desktop views."""

from __future__ import annotations


def build_stylesheet() -> str:
    """Return the application stylesheet for the editorial-industrial theme."""
    return """
QWidget {
    background-color: #f3f1ec;
    color: #1f2933;
    font-family: "Bahnschrift", "Segoe UI", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background-color: #ece9e1;
}

QTabWidget::pane {
    border: 1px solid #c7c2b7;
    background: #faf8f3;
    border-radius: 12px;
    padding: 8px;
}

QTabBar::tab {
    background: #ddd8cc;
    color: #4b5563;
    border: 1px solid #c7c2b7;
    border-bottom: none;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    padding: 8px 14px;
    margin-right: 4px;
    font-family: "Cambria", serif;
    font-size: 14px;
}

QTabBar::tab:selected {
    background: #faf8f3;
    color: #12212f;
}

QGroupBox {
    border: 1px solid #c7c2b7;
    border-radius: 10px;
    margin-top: 12px;
    padding: 14px 12px 12px 12px;
    font-family: "Cambria", serif;
    font-size: 14px;
    font-weight: 600;
    background-color: #f8f5ee;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #243746;
}

QLineEdit,
QTextEdit,
QPlainTextEdit,
QSpinBox,
QTableWidget {
    background: #fffdf9;
    border: 1px solid #c7c2b7;
    border-radius: 8px;
    padding: 7px;
    selection-background-color: #d7b778;
    selection-color: #1d2831;
}

QLineEdit:focus,
QTextEdit:focus,
QSpinBox:focus,
QTableWidget:focus {
    border: 2px solid #b77b2b;
}

QLineEdit[invalid="true"] {
    border: 2px solid #a63636;
    background: #fff4f4;
}

QPushButton {
    background: #d9d1c2;
    color: #1f2933;
    border: 1px solid #bcae97;
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 600;
}

QPushButton:hover {
    background: #cfc5b2;
}

QPushButton:disabled {
    background: #e4dfd5;
    color: #8a8f96;
    border-color: #d2ccc1;
}

QPushButton[variant="primary"] {
    background: #2f4557;
    color: #f7f4ec;
    border-color: #223645;
}

QPushButton[variant="primary"]:hover {
    background: #203543;
}

QPushButton[variant="danger"] {
    background: #8c3328;
    color: #fff7f4;
    border-color: #6d241d;
}

QPushButton[variant="danger"]:hover {
    background: #74271f;
}

QProgressBar {
    border: 1px solid #c7c2b7;
    border-radius: 7px;
    text-align: center;
    background: #ebe6db;
    min-height: 20px;
    color: #223645;
    font-weight: 600;
}

QProgressBar::chunk {
    background-color: #b77b2b;
    border-radius: 6px;
}

QHeaderView::section {
    background-color: #e2dccf;
    color: #233443;
    border: 1px solid #c7c2b7;
    padding: 6px;
    font-weight: 600;
}

QCheckBox {
    spacing: 6px;
    padding-top: 2px;
    padding-bottom: 2px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #6c7a88;
    border-radius: 4px;
    background: #f9f7f1;
}

QCheckBox::indicator:unchecked:hover {
    border-color: #2f4557;
    background: #eef2f4;
}

QCheckBox::indicator:checked {
    border: 2px solid #1f3342;
    background: #2f4557;
}

QCheckBox::indicator:checked:hover {
    background: #203543;
}

QCheckBox::indicator:disabled {
    border-color: #b5b2aa;
    background: #e6e3db;
}

QSplitter::handle {
    background: #d4cec2;
}

QSplitter::handle:vertical {
    height: 8px;
}

QSplitter::handle:horizontal {
    width: 8px;
}

QSplitter::handle:hover {
    background: #bfa57a;
}

QLabel[role="hint"] {
    color: #5f6b78;
}

QLabel[role="status"] {
    padding: 4px 9px;
    border-radius: 11px;
    font-weight: 600;
}

QLabel[state="idle"] {
    background: #ddd8cc;
    color: #2c3c4a;
}

QLabel[state="running"] {
    background: #d7b778;
    color: #392204;
}

QLabel[state="success"] {
    background: #8ea889;
    color: #102311;
}

QLabel[state="error"] {
    background: #d39a94;
    color: #3b0f0b;
}
"""
