from __future__ import annotations


def build_app_stylesheet(config: dict) -> str:
    theme = config["ui"]["theme"]
    sidebar_bg = "#0B1F3A"
    sidebar_hover = "#12325C"
    sidebar_active = theme["accent"]
    return f"""
    QWidget {{
        background: {theme["bg"]};
        color: {theme["text"]};
        font-family: "Segoe UI";
        font-size: 10pt;
    }}

    QMainWindow {{
        background: {theme["bg"]};
    }}

    QPushButton {{
        border: 0;
        border-radius: 6px;
        padding: 9px 14px;
        background: {theme["accent"]};
        color: white;
        font-weight: 600;
    }}

    QPushButton:hover {{
        background: {theme["accent_dark"]};
    }}

    QPushButton:disabled {{
        background: {theme["border"]};
        color: {theme["text_muted"]};
    }}

    QPushButton[secondary="true"] {{
        background: {theme["bg2"]};
        color: {theme["text"]};
    }}

    QPushButton[secondary="true"]:hover {{
        background: {theme["border"]};
    }}

    QPushButton[danger="true"] {{
        background: {theme["danger"]};
    }}

    QPushButton[danger="true"]:hover {{
        background: #9F2F24;
    }}

    QLineEdit {{
        background: white;
        border: 1px solid {theme["border"]};
        border-radius: 6px;
        padding: 8px 10px;
    }}

    QLineEdit:focus {{
        border: 1px solid {theme["accent"]};
    }}

    QComboBox {{
        background: white;
        border: 1px solid {theme["border"]};
        border-radius: 6px;
        padding: 7px 10px;
    }}

    QTextEdit {{
        background: white;
        border: 1px solid {theme["border"]};
        border-radius: 6px;
        padding: 8px 10px;
    }}

    QPlainTextEdit {{
        background: white;
        border: 0;
        padding: 8px 10px;
    }}

    QCheckBox {{
        spacing: 6px;
    }}

    QProgressBar {{
        border: 1px solid {theme["border"]};
        border-radius: 5px;
        background: white;
        height: 10px;
        text-align: center;
    }}

    QProgressBar::chunk {{
        border-radius: 5px;
        background: {theme["accent"]};
    }}

    QSplitter::handle {{
        background: {theme["bg"]};
    }}

    QTableWidget {{
        background: white;
        border: 1px solid {theme["border"]};
        border-radius: 6px;
        gridline-color: {theme["border"]};
        selection-background-color: #DDEBFF;
    }}

    QHeaderView::section {{
        background: {theme["bg2"]};
        color: {theme["text_muted"]};
        border: 0;
        border-bottom: 1px solid {theme["border"]};
        padding: 7px;
        font-weight: 700;
    }}

    QLabel#PageTitle {{
        font-size: 22pt;
        font-weight: 700;
    }}

    QLabel#PageSubtitle {{
        color: {theme["text_muted"]};
    }}

    QFrame#Sidebar {{
        background: {sidebar_bg};
    }}

    QLabel#SidebarTitle,
    QLabel#SidebarSubtitle {{
        background: {sidebar_bg};
        color: white;
    }}

    QLabel#SidebarSubtitle {{
        color: #BFDBFE;
    }}

    QPushButton#NavButton {{
        background: {sidebar_bg};
        color: #E5E7EB;
        text-align: left;
        padding: 11px 14px;
    }}

    QPushButton#NavButton:hover {{
        background: {sidebar_hover};
    }}

    QPushButton#NavButton[active="true"] {{
        background: {sidebar_active};
        color: white;
    }}

    QFrame#Card {{
        background: {theme["surface"]};
        border: 1px solid {theme["border"]};
        border-radius: 8px;
    }}

    QFrame#SubPanel {{
        background: {theme["bg2"]};
        border: 1px solid {theme["border"]};
        border-radius: 6px;
    }}

    QLabel#Muted {{
        color: {theme["text_muted"]};
    }}

    QLabel#Badge {{
        border-radius: 12px;
        padding: 4px 9px;
        font-weight: 700;
    }}
    """


def status_colors(config: dict, status: str) -> tuple[str, str]:
    theme = config["ui"]["theme"]
    normalized = status.upper()
    if "ERRORE" in normalized:
        return "#FEE2E2", theme["danger"]
    if "ATTENZIONE" in normalized:
        return "#FEF3C7", theme["warning"]
    if "OK" in normalized:
        return "#DCFCE7", theme["success"]
    return "#DBEAFE", theme["accent"]
