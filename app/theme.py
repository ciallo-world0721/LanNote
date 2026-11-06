from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

COLORS = {
    "yellow": {"label": "鹅黄", "swatch": "#EFC63F"},
    "mint": {"label": "薄荷", "swatch": "#7CC79B"},
    "sky": {"label": "晴空", "swatch": "#7FB7DE"},
    "rose": {"label": "樱粉", "swatch": "#E899A8"},
    "lilac": {"label": "雾紫", "swatch": "#B3A0DC"},
}

DEFAULT_COLOR = "yellow"


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
