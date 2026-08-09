"""Design tokens and the stylesheet built from them.

Los valores vienen de la UI de proxy-local, para que las dos apps se vean como una
sola familia. Lo que se agrega acá son las reglas de las piezas que ese CLI no
tenía: barra de progreso, tablas y filas de entorno con dos niveles.
"""

from __future__ import annotations

from dataclasses import dataclass


UI_FONTS = ["Inter", "Cantarell", "Noto Sans", "DejaVu Sans", "sans-serif"]
MONO_FONTS = [
    "JetBrains Mono",
    "Fira Code",
    "Source Code Pro",
    "DejaVu Sans Mono",
    "monospace",
]

RADIUS = 12
RADIUS_SMALL = 8


@dataclass(frozen=True, slots=True)
class Palette:
    name: str
    background: str
    surface: str
    elevated: str
    border: str
    border_strong: str
    text: str
    muted: str
    faint: str
    accent: str
    accent_hover: str
    accent_text: str
    success: str
    danger: str
    warning: str
    track: str
    shadow: str


DARK = Palette(
    name="dark",
    background="#13151a",
    surface="#191c23",
    elevated="#20242d",
    border="#2a2f3a",
    border_strong="#39404e",
    text="#e8ebf2",
    muted="#949cac",
    faint="#6b7382",
    accent="#6c8cff",
    accent_hover="#8099ff",
    accent_text="#ffffff",
    success="#3fcf8e",
    danger="#ff6b6b",
    warning="#ffb84d",
    track="#333a47",
    shadow="rgba(0, 0, 0, 0.45)",
)

LIGHT = Palette(
    name="light",
    background="#f5f6f8",
    surface="#ffffff",
    elevated="#ffffff",
    border="#e3e6eb",
    border_strong="#cfd4dd",
    text="#181b21",
    muted="#666e7d",
    faint="#8b93a1",
    accent="#3b6ef6",
    accent_hover="#2c5be0",
    accent_text="#ffffff",
    success="#0f9d63",
    danger="#d94848",
    warning="#b0730c",
    track="#d7dbe2",
    shadow="rgba(15, 20, 30, 0.12)",
)


def stylesheet(palette: Palette) -> str:
    ui_font = ", ".join(f'"{name}"' for name in UI_FONTS)
    mono_font = ", ".join(f'"{name}"' for name in MONO_FONTS)
    return f"""
    * {{
        font-family: {ui_font};
        outline: none;
    }}

    QWidget {{
        color: {palette.text};
        background: transparent;
    }}

    QMainWindow, #Root {{
        background: {palette.background};
    }}

    /* ---- sidebar ---- */

    #Sidebar {{
        background: {palette.surface};
        border-right: 1px solid {palette.border};
    }}

    #BrandName {{
        font-size: 17px;
        font-weight: 700;
        letter-spacing: 0.2px;
    }}

    #BrandSubtitle {{
        color: {palette.faint};
        font-size: 11px;
    }}

    #SidebarSection {{
        color: {palette.faint};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1.1px;
    }}

    #SidebarItem {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: {RADIUS_SMALL}px;
        text-align: left;
    }}

    #SidebarItem:hover {{
        background: {palette.elevated};
    }}

    #SidebarItem[selected="true"] {{
        background: {palette.elevated};
        border: 1px solid {palette.border_strong};
    }}

    #SidebarItemTitle {{
        font-size: 13px;
        font-weight: 600;
    }}

    #SidebarItemSubtitle {{
        color: {palette.faint};
        font-size: 11px;
    }}

    /* La fila de entorno padre es un encabezado que se abre y cierra, no un
       destino: se distingue del tipo por peso y tamaño, no por color. */
    #SidebarGroupTitle {{
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.4px;
        color: {palette.muted};
    }}

    #Chevron {{
        color: {palette.faint};
        font-size: 10px;
    }}

    #FooterText {{
        color: {palette.muted};
        font-size: 11px;
    }}

    /* ---- detail ---- */

    #DetailTitle {{
        font-size: 22px;
        font-weight: 700;
    }}

    #DetailSubtitle {{
        color: {palette.muted};
        font-size: 12px;
    }}

    #Card {{
        background: {palette.surface};
        border: 1px solid {palette.border};
        border-radius: {RADIUS}px;
    }}

    #CardTitle {{
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
        color: {palette.faint};
    }}

    #FieldLabel {{
        color: {palette.muted};
        font-size: 12px;
    }}

    #FieldValue {{
        font-family: {mono_font};
        font-size: 12px;
    }}

    #FieldValueMuted {{
        font-family: {mono_font};
        font-size: 12px;
        color: {palette.faint};
    }}

    #Separator {{
        background: {palette.border};
        max-height: 1px;
        min-height: 1px;
        border: none;
    }}

    #EmptyTitle {{
        font-size: 16px;
        font-weight: 600;
        color: {palette.muted};
    }}

    #EmptyBody {{
        color: {palette.faint};
        font-size: 12px;
    }}

    /* ---- pills ---- */

    #Pill {{
        font-size: 11px;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 9px;
        background: {palette.elevated};
        color: {palette.muted};
        border: 1px solid {palette.border};
    }}

    #Pill[tone="on"] {{
        color: {palette.success};
        border: 1px solid {palette.success};
        background: transparent;
    }}

    #Pill[tone="warn"] {{
        color: {palette.warning};
        border: 1px solid {palette.warning};
        background: transparent;
    }}

    #Pill[tone="bad"] {{
        color: {palette.danger};
        border: 1px solid {palette.danger};
        background: transparent;
    }}

    #Pill[tone="info"] {{
        color: {palette.accent};
        border: 1px solid {palette.accent};
        background: transparent;
    }}

    /* ---- buttons ---- */

    QPushButton {{
        background: {palette.elevated};
        color: {palette.text};
        border: 1px solid {palette.border_strong};
        border-radius: {RADIUS_SMALL}px;
        padding: 7px 14px;
        font-size: 12px;
        font-weight: 600;
    }}

    QPushButton:hover {{
        border-color: {palette.accent};
    }}

    QPushButton:disabled {{
        color: {palette.faint};
        border-color: {palette.border};
    }}

    QPushButton#Primary {{
        background: {palette.accent};
        color: {palette.accent_text};
        border: 1px solid {palette.accent};
    }}

    QPushButton#Primary:hover {{
        background: {palette.accent_hover};
        border-color: {palette.accent_hover};
    }}

    QPushButton#Primary:disabled {{
        background: {palette.track};
        border-color: {palette.track};
        color: {palette.faint};
    }}

    QPushButton#Danger {{
        color: {palette.danger};
        border-color: {palette.border_strong};
    }}

    QPushButton#Danger:hover {{
        border-color: {palette.danger};
    }}

    QPushButton#Ghost {{
        background: transparent;
        border-color: transparent;
        color: {palette.muted};
        padding: 6px 8px;
    }}

    QPushButton#Ghost:hover {{
        color: {palette.text};
        background: {palette.elevated};
    }}

    QPushButton#IconButton {{
        background: transparent;
        border-color: transparent;
        color: {palette.muted};
        font-size: 16px;
        padding: 2px 4px;
    }}

    QPushButton#IconButton:hover {{
        color: {palette.text};
        background: {palette.elevated};
    }}

    QPushButton#Chip {{
        background: transparent;
        border: 1px solid {palette.border};
        color: {palette.faint};
        border-radius: 9px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 600;
    }}

    QPushButton#Chip:checked {{
        color: {palette.accent};
        border-color: {palette.accent};
    }}

    /* ---- inputs ---- */

    QLineEdit {{
        background: {palette.background};
        border: 1px solid {palette.border_strong};
        border-radius: {RADIUS_SMALL}px;
        padding: 8px 10px;
        font-family: {mono_font};
        font-size: 12px;
        selection-background-color: {palette.accent};
        selection-color: {palette.accent_text};
    }}

    QLineEdit:focus {{
        border-color: {palette.accent};
    }}

    QLineEdit[invalid="true"] {{
        border-color: {palette.danger};
    }}

    #MfaCode {{
        font-size: 24px;
        font-weight: 700;
        letter-spacing: 10px;
        padding: 12px;
    }}

    QLabel#FieldHint {{
        color: {palette.faint};
        font-size: 11px;
    }}

    QLabel#FieldError {{
        color: {palette.danger};
        font-size: 11px;
    }}

    QCheckBox {{
        font-size: 12px;
        color: {palette.muted};
        spacing: 7px;
    }}

    QCheckBox::indicator {{
        width: 15px;
        height: 15px;
        border-radius: 4px;
        border: 1px solid {palette.border_strong};
        background: {palette.background};
    }}

    QCheckBox::indicator:checked {{
        background: {palette.accent};
        border-color: {palette.accent};
    }}

    QComboBox {{
        background: {palette.background};
        border: 1px solid {palette.border_strong};
        border-radius: {RADIUS_SMALL}px;
        padding: 7px 10px;
        font-family: {mono_font};
        font-size: 12px;
        min-width: 180px;
    }}

    QComboBox:hover {{
        border-color: {palette.accent};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}

    /* Algunos combos muestran nombres, no valores tecnicos: van sin mono. */
    QComboBox#TextCombo, QComboBox#TextCombo QAbstractItemView {{
        font-family: {ui_font};
        min-width: 150px;
    }}

    QComboBox QAbstractItemView {{
        background: {palette.surface};
        border: 1px solid {palette.border_strong};
        border-radius: {RADIUS_SMALL}px;
        padding: 4px;
        font-family: {mono_font};
        font-size: 12px;
        selection-background-color: {palette.elevated};
        selection-color: {palette.text};
        outline: none;
    }}

    /* ---- tables: dumps remotos, locales e historial ---- */

    QTreeWidget, QTableWidget {{
        background: {palette.background};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SMALL}px;
        font-size: 12px;
        alternate-background-color: {palette.surface};
        selection-background-color: {palette.elevated};
        selection-color: {palette.text};
        outline: none;
    }}

    QTreeWidget::item, QTableWidget::item {{
        padding: 6px 8px;
        border: none;
    }}

    QTreeWidget::item:selected, QTableWidget::item:selected {{
        background: {palette.elevated};
        color: {palette.text};
    }}

    QHeaderView::section {{
        background: {palette.surface};
        color: {palette.faint};
        border: none;
        border-bottom: 1px solid {palette.border};
        padding: 7px 8px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.8px;
    }}

    /* ---- progreso ---- */

    QProgressBar {{
        background: {palette.track};
        border: none;
        border-radius: 5px;
        height: 8px;
        text-align: center;
        color: transparent;
    }}

    QProgressBar::chunk {{
        background: {palette.accent};
        border-radius: 5px;
    }}

    #ProgressText {{
        font-family: {mono_font};
        font-size: 11px;
        color: {palette.muted};
    }}

    /* ---- log ---- */

    #LogView {{
        background: {palette.background};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SMALL}px;
        font-family: {mono_font};
        font-size: 11px;
        color: {palette.muted};
        padding: 8px;
        selection-background-color: {palette.accent};
        selection-color: {palette.accent_text};
    }}

    /* ---- banner ---- */

    #Banner {{
        background: {palette.elevated};
        border: 1px solid {palette.danger};
        border-radius: {RADIUS_SMALL}px;
    }}

    #BannerText {{
        color: {palette.danger};
        font-size: 12px;
    }}

    #Notice {{
        background: {palette.elevated};
        border: 1px solid {palette.warning};
        border-radius: {RADIUS_SMALL}px;
    }}

    #NoticeText {{
        color: {palette.warning};
        font-size: 12px;
    }}

    /* ---- scrollbars ---- */

    QScrollArea {{
        border: none;
        background: transparent;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical {{
        background: {palette.track};
        border-radius: 5px;
        min-height: 28px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {palette.border_strong};
    }}

    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
        background: none;
        border: none;
        height: 0;
        width: 0;
    }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}

    QScrollBar::handle:horizontal {{
        background: {palette.track};
        border-radius: 5px;
        min-width: 28px;
    }}

    QAbstractScrollArea::corner {{
        background: transparent;
        border: none;
    }}

    /* ---- tabs ---- */

    QTabWidget::pane {{
        border: none;
        border-top: 1px solid {palette.border};
        top: -1px;
    }}

    QTabBar::tab {{
        background: transparent;
        color: {palette.muted};
        border: none;
        border-bottom: 2px solid transparent;
        padding: 8px 14px;
        margin-right: 4px;
        font-size: 12px;
        font-weight: 600;
    }}

    QTabBar::tab:hover {{
        color: {palette.text};
    }}

    QTabBar::tab:selected {{
        color: {palette.accent};
        border-bottom: 2px solid {palette.accent};
    }}

    /* ---- dialogs and menus ---- */

    QDialog {{
        background: {palette.background};
    }}

    #DialogTitle {{
        font-size: 16px;
        font-weight: 700;
    }}

    QMenu {{
        background: {palette.surface};
        border: 1px solid {palette.border};
        border-radius: {RADIUS_SMALL}px;
        padding: 6px;
    }}

    QMenu::item {{
        padding: 6px 26px 6px 12px;
        border-radius: 6px;
        font-size: 12px;
    }}

    QMenu::item:selected {{
        background: {palette.elevated};
    }}

    QMenu::item:disabled {{
        color: {palette.faint};
    }}

    QMenu::separator {{
        height: 1px;
        background: {palette.border};
        margin: 5px 8px;
    }}

    QToolTip {{
        background: {palette.elevated};
        color: {palette.text};
        border: 1px solid {palette.border_strong};
        border-radius: 6px;
        padding: 4px 7px;
        font-size: 11px;
    }}
    """
