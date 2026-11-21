"""Accessible, high-contrast look of the original app, as a Qt style sheet."""
BLUE = "#0b5394"
GREEN = "#0b6e3a"
GREEN_DARK = "#064d28"
FOCUS = "#ffbf00"
REPORT_BG = "#f5f9ff"


def stylesheet(rtl: bool) -> str:
    lead = "right" if rtl else "left"
    return f"""
QWidget {{ font-size: 12pt; color: #111; }}
QMainWindow, QScrollArea, #content {{ background: #ffffff; }}
QLabel#title {{ font-size: 20pt; font-weight: 700; }}
QLabel#h2 {{ font-size: 16pt; font-weight: 700; margin-top: 8px; }}
QLabel#h3 {{ font-size: 13.5pt; font-weight: 700; }}
QLabel#caption {{ color: #4a5568; font-size: 10.5pt; }}
QPushButton {{
    font-size: 13pt; font-weight: 700; padding: 9px 20px; border-radius: 10px;
    border: 3px solid {BLUE}; background: #ffffff;
}}
QPushButton:hover {{ background: #e3ecf7; }}
QPushButton:focus {{ border-color: {FOCUS}; }}
QPushButton:disabled {{ color: #8a8a8a; border-color: #b8c4d4; }}
QPushButton[kind="download"] {{ background: {GREEN}; color: #ffffff; border-color: {GREEN_DARK}; }}
QPushButton[kind="download"]:hover {{ background: {GREEN_DARK}; }}
QPushButton[kind="download"]:focus {{ border-color: {FOCUS}; }}
QPushButton[kind="solid"] {{ background: {BLUE}; color: #ffffff; }}
QPushButton[kind="solid"]:focus {{ border-color: {FOCUS}; }}
QPushButton[kind="quiet"] {{ border: 2px solid #c9d3e0; background: #f8f8f8; font-size: 11.5pt; padding: 6px 14px; }}
QPushButton[kind="section"] {{ text-align: {lead}; border: 1px solid #c9d3e0; background: #f7f9fc; }}
QLabel#report {{
    background: {REPORT_BG}; border-{lead}: 6px solid {BLUE}; border-radius: 8px;
    padding: 14px 16px; color: #111; line-height: 200%;
}}
QLabel[tone="info"] {{ background: #eaf2fd; border-{lead}: 6px solid {BLUE}; border-radius: 8px; padding: 10px 14px; color: #13386b; }}
QLabel[tone="warning"] {{ background: #fff8e1; border-{lead}: 6px solid #e2b13c; border-radius: 8px; padding: 10px 14px; color: #5a4300; }}
QLabel[tone="error"] {{ background: #fdecee; border-{lead}: 6px solid #a10d20; border-radius: 8px; padding: 10px 14px; color: #a10d20; }}
QLabel[tone="success"] {{ background: #e8f6ee; border-{lead}: 6px solid {GREEN}; border-radius: 8px; padding: 10px 14px; color: {GREEN_DARK}; }}
QFrame#dropzone {{ border: 3px dashed #7fa1cc; border-radius: 12px; background: #f3f6fa; }}
QFrame#card {{ border: 1px solid #d5dde8; border-radius: 12px; background: #ffffff; }}
QFrame#userMsg {{ border-radius: 12px; background: #f1f4f8; }}
QFrame#aiMsg {{ border: 1px solid #d5dde8; border-radius: 12px; background: #ffffff; }}
QLineEdit, QPlainTextEdit, QComboBox {{ border: 2px solid #7d8ba0; border-radius: 8px; padding: 6px 8px; background: #fff; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color: {FOCUS}; }}
QTableWidget {{ gridline-color: #d5dde8; font-size: 11pt; }}
QHeaderView::section {{ background: #eef2f7; font-weight: 700; padding: 6px; border: 0; }}
QProgressBar {{ border: 2px solid {BLUE}; border-radius: 6px; text-align: center; height: 22px; }}
QProgressBar::chunk {{ background: {BLUE}; }}
QCheckBox {{ font-weight: 600; }}
QCheckBox::indicator {{ width: 20px; height: 20px; }}
"""
