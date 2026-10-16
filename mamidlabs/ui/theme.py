"""Application theme (a small Qt stylesheet, follows the system palette)."""

from __future__ import annotations

STYLESHEET = """
QMainWindow, QWidget { background: #1e1f24; color: #e6e6e6; }
QTextBrowser#chat { background: #17181c; border: 1px solid #2c2e35; border-radius: 8px; }
QPlainTextEdit#input { background: #23252b; border: 1px solid #2c2e35; border-radius: 8px;
                       padding: 6px; }
QPushButton { background: #2f6fed; color: white; border: none; border-radius: 8px;
              padding: 8px 14px; }
QPushButton:disabled { background: #3a3d46; color: #8a8f99; }
QPushButton#stop { background: #c0392b; }
QComboBox, QLineEdit { background: #23252b; border: 1px solid #2c2e35; border-radius: 6px;
                       padding: 5px 8px; }
QCheckBox { padding: 4px; }
QStatusBar { background: #17181c; color: #9aa0aa; }
QLabel#header { font-weight: 600; }
"""
