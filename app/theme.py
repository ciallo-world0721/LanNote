from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

COLORS = {
    "yellow": {
        "label": "鹅黄",
        "bg": "#FFF4C2",
        "border": "#E7D391",
        "text": "#3E3524",
        "muted": "#9A8C63",
        "accent": "#8A6A14",
        "swatch": "#EFC63F",
    },
    "mint": {
        "label": "薄荷",
        "bg": "#DDF3E4",
        "border": "#B7DCC4",
        "text": "#243A2C",
        "muted": "#6B8F79",
        "accent": "#2C6B4A",
        "swatch": "#7CC79B",
    },
    "sky": {
        "label": "晴空",
        "bg": "#DCEEFB",
        "border": "#B4D5EC",
        "text": "#1F3347",
        "muted": "#64809A",
        "accent": "#285F88",
        "swatch": "#7FB7DE",
    },
    "rose": {
        "label": "樱粉",
        "bg": "#FBE0E4",
        "border": "#EFC2CA",
        "text": "#442A31",
        "muted": "#9B7079",
        "accent": "#9C4557",
        "swatch": "#E899A8",
    },
    "lilac": {
        "label": "雾紫",
        "bg": "#ECE6F7",
        "border": "#D3C7E9",
        "text": "#322B42",
        "muted": "#7C7098",
        "accent": "#5F4C93",
        "swatch": "#B3A0DC",
    },
}

ORDER = ["yellow", "mint", "sky", "rose", "lilac"]
DEFAULT_COLOR = "yellow"


def dot(name, size=16):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(COLORS[name]["accent"]), 1.3))
    p.setBrush(QColor(COLORS[name]["swatch"]))
    pad = 1.6
    p.drawEllipse(QRectF(pad, pad, size - 2 * pad, size - 2 * pad))
    p.end()
    return QIcon(pm)


def _icon_pixmap(size):
    # build_exe.py 还要用这个画 ico
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#F6C445"))
    p.drawRoundedRect(QRectF(0.03 * size, 0.03 * size, 0.94 * size, 0.94 * size), 0.2 * size, 0.2 * size)

    pen = QPen(QColor("#6F5210"))
    pen.setWidthF(max(1.4, 0.07 * size))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    for i, y in enumerate((0.33, 0.5, 0.67)):
        end = 0.72 if i < 2 else 0.55
        p.drawLine(QPointF(0.26 * size, y * size), QPointF(end * size, y * size))
    p.end()
    return pm


def icon():
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(_icon_pixmap(s))
    return ic
