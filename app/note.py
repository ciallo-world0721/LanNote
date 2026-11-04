from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QGuiApplication, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QMenu,
    QSizeGrip,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from theme import COLORS, DEFAULT_COLOR, ORDER, dot

MIN_W, MIN_H = 230, 180
DEF_W, DEF_H = 320, 320
SHADOW = 14


class TitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setCursor(Qt.OpenHandCursor)
        self._off = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._off = e.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._off is not None and e.buttons() & Qt.LeftButton:
            self.window().move(e.globalPosition().toPoint() - self._off)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._off = None
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(e)


class NoteWindow(QWidget):
    new_requested = Signal()
    saved = Signal(int)
    closed = Signal(int)

    def __init__(self, store, row, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(QSize(MIN_W, MIN_H))
        self.setWindowTitle("LanNote")
        self.setWindowIcon(QGuiApplication.windowIcon())

        self.store = store
        self.note_id = int(row["id"])
        self.color = row["color"] if row["color"] in COLORS else DEFAULT_COLOR
        self.fs = int(row["font_size"] or 12)
        self.pinned = bool(row["pinned"])
        self._closing = False

        self.tmSave = QTimer(self)
        self.tmSave.setSingleShot(True)
        self.tmSave.setInterval(450)
        self.tmSave.timeout.connect(self._save)

        self.tmGeo = QTimer(self)
        self.tmGeo.setSingleShot(True)
        self.tmGeo.setInterval(400)
        self.tmGeo.timeout.connect(self._save_geo)

        self._ui()
        self._load_geo(row)
        self._theme()
        self._pin_apply(save=False)
        self.text.setPlainText(row["content"] or "")

    def _ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW, SHADOW, SHADOW, SHADOW)
        outer.setSpacing(0)

        self.card = QFrame(self)
        self.card.setObjectName("card")
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.bar = TitleBar(self.card)
        top = QHBoxLayout(self.bar)
        top.setContentsMargins(12, 6, 8, 0)
        top.setSpacing(2)

        self.btnColor = self._btn("", "颜色")
        self.btnColor.setIconSize(QSize(16, 16))
        self.btnColor.setIcon(dot(self.color))
        self.btnColor.setFixedSize(26, 26)
        self.btnColor.clicked.connect(self._color_menu)

        self.btnPin = self._btn("↑", "置顶")
        self.btnPin.setFixedSize(26, 26)
        self.btnPin.clicked.connect(self._pin)

        self.btnNew = self._btn("＋", "新建便签 (Ctrl+N)")
        self.btnNew.setFixedSize(26, 26)
        self.btnNew.clicked.connect(self.new_requested.emit)

        self.btnClose = self._btn("✕", "关闭（内容自动保存）")
        self.btnClose.setFixedSize(26, 26)
        self.btnClose.clicked.connect(self.close)

        top.addWidget(self.btnColor)
        top.addStretch(1)
        top.addWidget(self.btnPin)
        top.addWidget(self.btnNew)
        top.addWidget(self.btnClose)
        lay.addWidget(self.bar)

        self.text = QTextEdit(self.card)
        self.text.setAcceptRichText(False)
        self.text.setFrameShape(QFrame.NoFrame)
        self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.text.setPlaceholderText("写点什么…")
        self.text.setTabChangesFocus(False)
        self.text.document().setDocumentMargin(0)
        self.text.textChanged.connect(self._save_later)
        self.text.setContextMenuPolicy(Qt.CustomContextMenu)
        self.text.customContextMenuRequested.connect(self._menu)
        self.text.installEventFilter(self)
        lay.addWidget(self.text, 1)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 4, 4)
        row.addStretch(1)
        grip = QSizeGrip(self.card)
        grip.setFixedSize(16, 16)
        row.addWidget(grip)
        lay.addLayout(row)

        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self.new_requested.emit)
        self.setWindowOpacity(0.985)

    def _btn(self, txt, tip):
        b = QToolButton(self.card)
        b.setText(txt)
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        b.setAutoRaise(True)
        b.setFocusPolicy(Qt.NoFocus)
        return b

    def _theme(self):
        c = COLORS[self.color]
        self.card.setStyleSheet(
            f"#card {{ background: {c['bg']}; border: 1px solid {c['border']}; border-radius: 12px; }}"
        )
        self.bar.setStyleSheet(
            "QToolButton { border: none; background: transparent;"
            f" color: {c['accent']}; font-size: 13px; border-radius: 6px; }}"
            "QToolButton:hover { background: rgba(0, 0, 0, 0.07); }"
            "QToolButton:pressed { background: rgba(0, 0, 0, 0.13); }"
            'QToolButton[active="true"] { background: rgba(0, 0, 0, 0.10); }'
        )
        self.text.setStyleSheet(
            "QTextEdit { background: transparent; border: none;"
            f" color: {c['text']}; padding: 3px 14px 6px 14px;"
            " selection-background-color: rgba(0, 0, 0, 0.16); }"
            "QScrollBar:vertical { background: transparent; width: 7px; margin: 0px 3px 8px 0px; }"
            "QScrollBar::handle:vertical { background: rgba(0, 0, 0, 0.16);"
            " border-radius: 3px; min-height: 24px; }"
            "QScrollBar::handle:vertical:hover { background: rgba(0, 0, 0, 0.28); }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )
        pal = self.text.palette()
        pal.setColor(QPalette.PlaceholderText, QColor(c["muted"]))
        self.text.setPalette(pal)
        self.btnColor.setIcon(dot(self.color))
        self._font()

    def _font(self):
        f = QFont("Microsoft YaHei UI")
        f.setPointSizeF(self.fs)
        self.text.setFont(f)

    def _menu(self, pos):
        m = QMenu(self)
        sel = self.text.textCursor().hasSelection()

        undo = m.addAction("撤销")
        undo.setEnabled(self.text.document().isUndoAvailable())
        undo.triggered.connect(self.text.undo)
        redo = m.addAction("重做")
        redo.setEnabled(self.text.document().isRedoAvailable())
        redo.triggered.connect(self.text.redo)
        m.addSeparator()
        cut = m.addAction("剪切")
        cut.setEnabled(sel)
        cut.triggered.connect(self.text.cut)
        copy = m.addAction("复制")
        copy.setEnabled(sel)
        copy.triggered.connect(self.text.copy)
        paste = m.addAction("粘贴")
        paste.setEnabled(bool(QGuiApplication.clipboard().text()))
        paste.triggered.connect(self.text.paste)
        m.addSeparator()
        m.addAction("全选").triggered.connect(self.text.selectAll)
        m.exec(self.text.mapToGlobal(pos))

    def _color_menu(self):
        m = QMenu(self)
        for k in ORDER:
            a = QAction(dot(k), COLORS[k]["label"], m)
            a.setCheckable(True)
            a.setChecked(k == self.color)
            a.triggered.connect(lambda checked=False, name=k: self._set_color(name))
            m.addAction(a)
        m.exec(QCursor.pos())

    def _set_color(self, name):
        self.color = name
        self._theme()
        self.store.update(self.note_id, color=name)
        self.saved.emit(self.note_id)

    def _pin(self):
        self.pinned = not self.pinned
        self._pin_apply()

    def _pin_apply(self, save=True):
        # Tool 窗口改 flag 后要重新 show 才生效
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.pinned)
        self.btnPin.setToolTip("取消置顶" if self.pinned else "置顶")
        self.btnPin.setProperty("active", self.pinned)
        self.btnPin.style().unpolish(self.btnPin)
        self.btnPin.style().polish(self.btnPin)
        if save:
            self.store.update(self.note_id, pinned=int(self.pinned))
            self.saved.emit(self.note_id)
        if self.isVisible():
            self.show()

    def _load_geo(self, row):
        # 存的是带阴影那圈的窗口坐标，换屏幕可能偏出去
        w = max(int(row["w"] or DEF_W), MIN_W)
        h = max(int(row["h"] or DEF_H), MIN_H)
        x, y = row["x"], row["y"]
        if x is None or y is None:
            x, y = self._center(w, h)
        else:
            x, y = int(x), int(y)
            if not self._on_screen(QRect(x, y, w, h)):
                x, y = self._center(w, h)
        self.setGeometry(x, y, w, h)

    @staticmethod
    def _on_screen(r):
        for s in QGuiApplication.screens():
            if s.availableGeometry().intersects(r):
                return True
        return False

    @staticmethod
    def _center(w, h):
        s = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        a = s.availableGeometry()
        return a.center().x() - w // 2, a.center().y() - h // 2

    def focus(self):
        self.raise_()
        self.activateWindow()
        self.text.setFocus()

    def _save_later(self):
        if not self._closing:
            self.tmSave.start()

    def _save(self):
        if self._closing:
            return
        self.store.update(self.note_id, content=self.text.toPlainText(), font_size=self.fs)
        self.saved.emit(self.note_id)

    def _save_geo(self):
        if self._closing:
            return
        g = self.geometry()
        self.store.update(self.note_id, x=g.x(), y=g.y(), w=g.width(), h=g.height())

    def moveEvent(self, e):
        if self.isVisible():
            self.tmGeo.start()
        super().moveEvent(e)

    def resizeEvent(self, e):
        if self.isVisible():
            self.tmGeo.start()
        super().resizeEvent(e)

    def eventFilter(self, obj, e):
        # Ctrl+滚轮调字号
        if obj is self.text and e.type() == QEvent.Wheel and e.modifiers() & Qt.ControlModifier:
            step = 1 if e.angleDelta().y() > 0 else -1
            self.fs = max(8, min(30, self.fs + step))
            self._font()
            self._save()
            return True
        return super().eventFilter(obj, e)

    def closeEvent(self, e):
        # 先存再关，_closing 挡住定时器
        self._closing = True
        self.tmSave.stop()
        self.tmGeo.stop()
        self.store.update(self.note_id, content=self.text.toPlainText(), font_size=self.fs)
        g = self.geometry()
        self.store.update(self.note_id, x=g.x(), y=g.y(), w=g.width(), h=g.height())
        super().closeEvent(e)
        self.closed.emit(self.note_id)
