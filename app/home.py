from datetime import datetime

from PySide6.QtCore import QPointF, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from theme import COLORS, DEFAULT_COLOR, icon

ROW_H = 80


def title(s):
    for line in (s or "").splitlines():
        line = line.strip()
        if line:
            return line[:60]
    return "空白便签"


def preview(s):
    lines = [x.strip() for x in (s or "").splitlines() if x.strip()]
    if len(lines) <= 1:
        return ""
    return " ".join(lines[1:])[:160]


def fmt(ts):
    try:
        t = datetime.fromtimestamp(ts)
    except (OSError, OverflowError, TypeError):
        return ""
    now = datetime.now()
    if t.date() == now.date():
        return t.strftime("今天 %H:%M")
    if (now.date() - t.date()).days == 1:
        return t.strftime("昨天 %H:%M")
    if t.year == now.year:
        return t.strftime("%m-%d %H:%M")
    return t.strftime("%Y-%m-%d")


class NoteItem(QStyledItemDelegate):
    def sizeHint(self, opt, idx):
        return QSize(opt.rect.width(), ROW_H)

    def paint(self, p, opt, idx):
        note = idx.data(Qt.UserRole) or {}
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)

        r = opt.rect.adjusted(4, 4, -4, -4)
        sel = bool(opt.state & QStyle.State_Selected)
        hov = bool(opt.state & QStyle.State_MouseOver)

        c = COLORS.get(note.get("color", DEFAULT_COLOR), COLORS[DEFAULT_COLOR])
        if sel:
            bg, bd = QColor("#FFFBEC"), QColor("#DDBB55")
        elif hov:
            bg, bd = QColor("#FBF9F3"), QColor("#E0DACA")
        else:
            bg, bd = QColor("#FFFFFF"), QColor("#E8E3D6")

        p.setPen(QPen(bd, 1))
        p.setBrush(bg)
        p.drawRoundedRect(r, 10, 10)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(c["swatch"]))
        p.drawEllipse(QPointF(r.left() + 20, r.center().y()), 6, 6)

        meta = 92
        f = QFont(opt.font)
        f.setPointSizeF(10.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#2F2B24"))
        tr = QRect(r.left() + 36, r.top() + 12, r.width() - 36 - meta - 12, 22)
        p.drawText(
            tr,
            Qt.AlignLeft | Qt.AlignVCenter,
            p.fontMetrics().elidedText(title(note.get("content", "")), Qt.ElideRight, tr.width()),
        )

        f2 = QFont(opt.font)
        f2.setPointSizeF(9)
        p.setFont(f2)
        p.setPen(QColor("#948C7B"))
        pr = QRect(r.left() + 36, r.top() + 37, r.width() - 50, 20)
        p.drawText(
            pr,
            Qt.AlignLeft | Qt.AlignVCenter,
            p.fontMetrics().elidedText(preview(note.get("content", "")), Qt.ElideRight, pr.width()),
        )

        f3 = QFont(opt.font)
        f3.setPointSizeF(8.5)
        p.setFont(f3)
        p.setPen(QColor("#A9A18F"))
        mr = QRect(r.right() - meta, r.top() + 14, meta - 14, 18)
        p.drawText(mr, Qt.AlignRight | Qt.AlignVCenter, fmt(note.get("updated", 0)))
        p.restore()


class Home(QWidget):
    new_note = Signal()
    open_note = Signal(int)
    delete_note = Signal(int)
    hidden = Signal()

    def __init__(self, store):
        super().__init__()
        self.db = store
        self.keep_in_tray = False
        self.setObjectName("home")
        self.setWindowTitle("LanNote")
        self.setWindowIcon(icon())
        self.resize(780, 560)
        self.setMinimumSize(560, 380)

        self.tmReload = QTimer(self)
        self.tmReload.setSingleShot(True)
        self.tmReload.setInterval(600)
        self.tmReload.timeout.connect(self.reload)

        self._ui()
        self._style()
        self.reload()

    def _ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 14)
        root.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(10)
        ico = QLabel()
        ico.setPixmap(icon().pixmap(28, 28))
        t = QLabel("LanNote")
        t.setObjectName("appTitle")
        self.btnNew = QPushButton("＋  新建便签")
        self.btnNew.setObjectName("newNote")
        self.btnNew.setCursor(Qt.PointingHandCursor)
        self.btnNew.clicked.connect(self.new_note.emit)
        head.addWidget(ico)
        head.addWidget(t)
        head.addStretch(1)
        head.addWidget(self.btnNew)
        root.addLayout(head)

        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("搜索便签…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.reload)
        root.addWidget(self.search)

        self.stack = QStackedWidget()
        self.stack.setObjectName("stack")

        self.lst = QListWidget()
        self.lst.setObjectName("notes")
        self.lst.setFrameShape(QFrame.NoFrame)
        self.lst.setItemDelegate(NoteItem(self.lst))
        self.lst.setSelectionMode(QAbstractItemView.SingleSelection)
        self.lst.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.lst.setMouseTracking(True)
        self.lst.setUniformItemSizes(True)
        self.lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lst.itemActivated.connect(self._open_item)
        self.lst.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lst.customContextMenuRequested.connect(self._menu)
        self.stack.addWidget(self.lst)

        empty = QWidget()
        el = QVBoxLayout(empty)
        el.setContentsMargins(0, 40, 0, 40)
        el.setSpacing(8)
        ei = QLabel()
        ei.setPixmap(icon().pixmap(56, 56))
        ei.setAlignment(Qt.AlignCenter)
        self.lblEmpty = QLabel("还没有便签")
        self.lblEmpty.setObjectName("emptyTitle")
        self.lblEmpty.setAlignment(Qt.AlignCenter)
        self.lblHint = QLabel("点右上角「新建便签」写一张")
        self.lblHint.setObjectName("emptyHint")
        self.lblHint.setAlignment(Qt.AlignCenter)
        el.addStretch(1)
        el.addWidget(ei)
        el.addSpacing(6)
        el.addWidget(self.lblEmpty)
        el.addWidget(self.lblHint)
        el.addStretch(1)
        self.stack.addWidget(empty)

        root.addWidget(self.stack, 1)

        self.lblCount = QLabel("")
        self.lblCount.setObjectName("count")
        root.addWidget(self.lblCount)

        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self.new_note.emit)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._focus_search)

    def _style(self):
        self.setStyleSheet(
            """
            QWidget#home { background: #F6F4EE; }
            QLabel#appTitle { font-size: 16pt; font-weight: 600; color: #2E2B24; }
            QPushButton#newNote {
                background: #F3C74F; color: #3A2E0B; border: none; border-radius: 8px;
                padding: 9px 18px; font-size: 10pt; font-weight: 600;
            }
            QPushButton#newNote:hover { background: #F7D268; }
            QPushButton#newNote:pressed { background: #E6B93C; }
            QLineEdit#search {
                background: #FFFFFF; border: 1px solid #E6E1D5; border-radius: 9px;
                padding: 9px 12px; color: #3A362E; font-size: 10pt;
            }
            QLineEdit#search:focus { border: 1px solid #D9BE6A; }
            QStackedWidget#stack { background: transparent; }
            QListWidget#notes { background: transparent; border: none; outline: 0; }
            QListWidget#notes::item { background: transparent; border: none; }
            QLabel#emptyTitle { color: #9A927F; font-size: 13pt; }
            QLabel#emptyHint { color: #B0A896; font-size: 9.5pt; }
            QLabel#count { color: #A39B89; font-size: 9pt; }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 0px; }
            QScrollBar::handle:vertical { background: #D8D1C0; border-radius: 4px; min-height: 30px; }
            QScrollBar::handle:vertical:hover { background: #C4BBA6; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
            """
        )

    def reload(self):
        # 搜索框每敲一下都重排，列表小无所谓
        q = self.search.text().strip().lower()
        all_rows = [dict(r) for r in self.db.notes()]
        rows = sorted(all_rows, key=lambda n: n.get("updated", 0), reverse=True)
        if q:
            rows = [n for n in rows if q in (n.get("content") or "").lower()]

        self.lst.clear()
        for n in rows:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, n)
            it.setSizeHint(QSize(0, ROW_H))
            self.lst.addItem(it)

        self.stack.setCurrentIndex(0 if rows else 1)
        if q:
            self.lblEmpty.setText("没有找到便签")
            self.lblHint.setText("换个关键词试试")
        else:
            self.lblEmpty.setText("还没有便签")
            self.lblHint.setText("点右上角「新建便签」写一张")

        self.lblCount.setText(f"共 {len(all_rows)} 张便签" if all_rows else "")

    def reload_later(self):
        self.tmReload.start()

    def show_up(self):
        self.reload()
        self.show()
        self.raise_()
        self.activateWindow()
        if self.search.text():
            self.search.setFocus()

    def _focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def _open_item(self, it):
        n = it.data(Qt.UserRole) or {}
        if n.get("id") is not None:
            self.open_note.emit(int(n["id"]))

    def _menu(self, pos):
        it = self.lst.itemAt(pos)
        if it is None:
            return
        n = it.data(Qt.UserRole) or {}
        m = QMenu(self)
        m.addAction("打开").triggered.connect(lambda: self.open_note.emit(int(n["id"])))
        m.addAction("删除").triggered.connect(lambda: self._del(n))
        m.exec(self.lst.viewport().mapToGlobal(pos))

    def _del(self, n):
        box = QMessageBox(self)
        box.setWindowTitle("LanNote")
        box.setIcon(QMessageBox.Warning)
        box.setText("删除这张便签？")
        box.setInformativeText(f"「{title(n.get('content', ''))}」删除后不能恢复。")
        ok = box.addButton("删除", QMessageBox.DestructiveRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is ok:
            self.delete_note.emit(int(n["id"]))

    def closeEvent(self, e):
        if self.keep_in_tray:
            e.ignore()
            self.hide()
            self.hidden.emit()
            return
        super().closeEvent(e)
