from datetime import datetime

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QPainter,
    QPalette,
    QShortcut,
    QTextBlockFormat,
    QTextCursor,
)
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
    QSplitter,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from theme import COLORS, DEFAULT_COLOR, icon

ROW_H = 88


def fmt(ts):
    t = datetime.fromtimestamp(ts)
    now = datetime.now()
    if t.date() == now.date():
        return t.strftime("今天 %H:%M")
    if (now.date() - t.date()).days == 1:
        return "昨天"
    if t.year == now.year:
        return t.strftime("%m月%d日")
    return t.strftime("%Y年%m月%d日")


def head(s):
    for line in s.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def brief(s):
    # drawText 不认 \n，压成一行，剩下的交给 elidedText 按像素截
    return " ".join(x.strip() for x in s.splitlines() if x.strip())


def name_of(n):
    return n["title"].strip() or head(n["content"]) or "无标题"


class Row(QStyledItemDelegate):
    def sizeHint(self, opt, idx):
        return QSize(opt.rect.width(), ROW_H)

    def paint(self, p, opt, idx):
        n = idx.data(Qt.UserRole)
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)

        r = opt.rect.adjusted(8, 2, -6, -2)
        sel = bool(opt.state & QStyle.State_Selected)
        hov = bool(opt.state & QStyle.State_MouseOver)
        if sel:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#FFF3C9"))
            p.drawRoundedRect(r, 9, 9)
        elif hov:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#F0ECE2"))
            p.drawRoundedRect(r, 9, 9)

        # 默认色不画色条，免得像列表符号
        c = COLORS[n["color"]]
        if sel or n["color"] != DEFAULT_COLOR:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c["swatch"]))
            p.drawRoundedRect(QRect(r.left() + 2, r.top() + 18, 3, ROW_H - 48), 1, 1)

        x = r.left() + 14
        w = r.width() - 26
        f = QFont(opt.font)

        f.setPointSizeF(10.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#2C2A24"))
        p.drawText(
            QRect(x, r.top() + 11, w, 21),
            Qt.AlignLeft | Qt.AlignVCenter,
            p.fontMetrics().elidedText(name_of(n), Qt.ElideRight, w),
        )

        f.setBold(False)
        f.setPointSizeF(9)
        p.setFont(f)
        p.setPen(QColor("#8F897A"))
        p.drawText(
            QRect(x, r.top() + 33, w, 19),
            Qt.AlignLeft | Qt.AlignVCenter,
            p.fontMetrics().elidedText(brief(n["content"]), Qt.ElideRight, w),
        )

        d = fmt(n["updated"])
        f.setPointSizeF(7.8)
        p.setFont(f)
        box = QRect(x, r.top() + 58, p.fontMetrics().horizontalAdvance(d) + 14, 18)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#F3E6C0") if sel else QColor("#EDE9DE"))
        p.drawRoundedRect(box, 4, 4)
        p.setPen(QColor("#97895F") if sel else QColor("#A6A08F"))
        p.drawText(box, Qt.AlignCenter, d)

        p.restore()


class Home(QWidget):
    def __init__(self, store):
        super().__init__()
        self.db = store
        self.keep = False
        self.cur = 0
        self.item = None
        self.quiet = False
        self.draft = False

        self.setObjectName("main")
        self.setWindowTitle("LanNote")
        self.setWindowIcon(icon())
        self.resize(1080, 700)
        self.setMinimumSize(760, 460)

        self.tm = QTimer(self)
        self.tm.setSingleShot(True)
        self.tm.setInterval(400)
        self.tm.timeout.connect(self.save)

        self.build()
        self.skin()
        self.reload()
        if self.lst.count():
            self.lst.setCurrentRow(0)

    def build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sp = QSplitter(Qt.Horizontal)
        self.sp.setChildrenCollapsible(False)
        root.addWidget(self.sp)

        side = QFrame()
        side.setObjectName("side")
        side.setMinimumWidth(210)
        side.setMaximumWidth(420)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 14, 12, 8)
        sl.setSpacing(9)

        bar = QHBoxLayout()
        bar.setContentsMargins(8, 0, 2, 0)
        t = QLabel("全部")
        t.setObjectName("all")
        self.btnNew = QToolButton()
        self.btnNew.setObjectName("add")
        self.btnNew.setText("＋")
        self.btnNew.setToolTip("新建（Ctrl+N）")
        self.btnNew.setCursor(Qt.PointingHandCursor)
        self.btnNew.setFocusPolicy(Qt.NoFocus)
        self.btnNew.clicked.connect(self.new)
        bar.addWidget(t)
        bar.addStretch(1)
        bar.addWidget(self.btnNew)
        sl.addLayout(bar)

        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("搜索")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.reload)
        sl.addWidget(self.search)

        self.lst = QListWidget()
        self.lst.setObjectName("notes")
        self.lst.setFrameShape(QFrame.NoFrame)
        self.lst.setItemDelegate(Row(self.lst))
        self.lst.setSelectionMode(QAbstractItemView.SingleSelection)
        self.lst.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.lst.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lst.setMouseTracking(True)
        self.lst.setUniformItemSizes(True)
        self.lst.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lst.customContextMenuRequested.connect(self.menu)
        self.lst.currentItemChanged.connect(self.switched)
        sl.addWidget(self.lst, 1)

        self.cnt = QLabel("")
        self.cnt.setObjectName("cnt")
        sl.addWidget(self.cnt)

        pane = QWidget()
        pane.setObjectName("pane")
        pl = QVBoxLayout(pane)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)

        top = QWidget()
        top.setFixedHeight(48)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(22, 10, 22, 0)
        tl.setSpacing(2)
        self.btnUndo = self.tb("↶", "撤销")
        self.btnRedo = self.tb("↷", "重做")
        tl.addWidget(self.btnUndo)
        tl.addWidget(self.btnRedo)
        pl.addWidget(top)

        self.stack = QStackedWidget()
        self.stack.setObjectName("stack")

        ed = QWidget()
        el = QVBoxLayout(ed)
        el.setContentsMargins(54, 8, 54, 26)
        el.setSpacing(0)

        self.title = QLineEdit()
        self.title.setObjectName("title")
        self.title.setPlaceholderText("无标题")
        self.title.setMaxLength(200)
        self.title.textChanged.connect(self.touched)
        el.addWidget(self.title)

        self.meta = QLabel("0 字")
        self.meta.setObjectName("meta")
        el.addWidget(self.meta)
        el.addSpacing(14)

        self.text = QTextEdit()
        self.text.setObjectName("body")
        self.text.setAcceptRichText(False)
        self.text.setFrameShape(QFrame.NoFrame)
        self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text.setTabChangesFocus(False)
        self.text.document().setDocumentMargin(0)
        self.text.textChanged.connect(self.touched)
        el.addWidget(self.text, 1)

        self.stack.addWidget(ed)

        blank = QWidget()
        bl = QVBoxLayout(blank)
        bl.addStretch(1)
        hint = QLabel("左边选一条，或者按 Ctrl+N 新写一条")
        hint.setObjectName("hint")
        hint.setAlignment(Qt.AlignCenter)
        bl.addWidget(hint)
        bl.addStretch(1)
        self.stack.addWidget(blank)

        pl.addWidget(self.stack, 1)

        self.sp.addWidget(side)
        self.sp.addWidget(pane)
        self.sp.setStretchFactor(0, 0)
        self.sp.setStretchFactor(1, 1)
        self.sp.setSizes([300, 780])

        self.btnUndo.clicked.connect(self.text.undo)
        self.btnRedo.clicked.connect(self.text.redo)
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self.new)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.focus_search)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.flush)

    def tb(self, txt, tip):
        b = QToolButton()
        b.setObjectName("tb")
        b.setText(txt)
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        b.setAutoRaise(True)
        b.setFocusPolicy(Qt.NoFocus)
        b.setFixedHeight(28)
        return b

    def skin(self):
        self.setStyleSheet(
            """
            QWidget#main { background: #FFFFFF; }
            QFrame#side { background: #F7F5EF; }
            QSplitter::handle { background: #ECE7DA; }
            QSplitter::handle:horizontal { width: 1px; }
            QLabel#all { color: #2E2C26; font-size: 12.5pt; font-weight: 600; }
            QToolButton#add {
                border: none; background: transparent; color: #6E6959;
                font-size: 15pt; padding: 0 8px; border-radius: 6px;
            }
            QToolButton#add:hover { background: #EBE6D9; }
            QLineEdit#search {
                background: #EFEBE1; border: 1px solid #EFEBE1; border-radius: 7px;
                padding: 7px 10px; color: #3A362E; font-size: 9.5pt;
            }
            QLineEdit#search:focus { background: #FFFFFF; border: 1px solid #E2D08A; }
            QListWidget#notes { background: transparent; border: none; outline: 0; }
            QListWidget#notes::item { background: transparent; border: none; }
            QLabel#cnt { color: #ADA694; font-size: 8.5pt; padding-left: 8px; }
            QWidget#pane { background: #FFFFFF; }
            QToolButton#tb {
                border: none; background: transparent; color: #918B7C;
                font-size: 13pt; padding: 0 7px; border-radius: 6px;
            }
            QToolButton#tb:hover { background: #F2EFE6; color: #4A463C; }
            QStackedWidget#stack { background: #FFFFFF; }
            QLineEdit#title {
                border: none; background: transparent; color: #23211C;
                font-size: 20.5pt; font-weight: 600; padding: 0;
            }
            QLabel#meta { color: #A9A392; font-size: 8.8pt; padding-top: 4px; }
            QTextEdit#body {
                border: none; background: transparent; color: #35322B;
                font-size: 12pt; selection-background-color: #FFE7A3;
                selection-color: #35322B;
            }
            QLabel#hint { color: #B7B1A0; font-size: 10.5pt; }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 2px 1px; }
            QScrollBar::handle:vertical { background: #DDD7C8; border-radius: 4px; min-height: 28px; }
            QScrollBar::handle:vertical:hover { background: #C9C1AE; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
            """
        )
        pal = self.title.palette()
        pal.setColor(QPalette.PlaceholderText, QColor("#C6C0B0"))
        self.title.setPalette(pal)
        pal = self.text.palette()
        pal.setColor(QPalette.PlaceholderText, QColor("#BDB7A6"))
        self.text.setPalette(pal)
        self.text.setPlaceholderText("开始写…")

    def reload(self, *_):
        q = self.search.text().strip().lower()
        rows = [dict(r) for r in self.db.notes()]
        if q:
            rows = [n for n in rows if q in n["title"].lower() or q in n["content"].lower()]

        self.quiet = True
        self.lst.clear()
        self.item = None
        for n in rows:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, n)
            self.lst.addItem(it)
            if self.cur and n["id"] == self.cur:
                self.lst.setCurrentItem(it)
                self.item = it
        self.quiet = False

        self.cnt.setText(f"{len(rows)} 条" if rows else "")
        if not self.cur and not self.draft:
            self.stack.setCurrentIndex(1)

    def find(self, nid):
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            if it.data(Qt.UserRole)["id"] == nid:
                return it
        return None

    def pick(self, nid):
        if nid == self.cur:
            return
        self.flush()
        r = self.db.get(nid)
        self.cur = r["id"]
        self.draft = False
        self.quiet = True
        self.title.setText(r["title"])
        self.text.setPlainText(r["content"])
        self.linespace()
        self.quiet = False
        self.meta.setText(f"{len(''.join((r['title'] + r['content']).split()))} 字")
        self.item = self.find(self.cur)
        self.quiet = True
        self.lst.setCurrentItem(self.item)
        self.quiet = False
        self.stack.setCurrentIndex(0)
        self.title.setFocus()

    def new(self):
        self.search.clear()
        if self.draft and not self.title.text().strip() and not self.text.toPlainText().strip():
            self.title.setFocus()
            return
        self.flush()
        self.cur = 0
        self.draft = True
        self.item = None
        self.quiet = True
        self.lst.setCurrentItem(None)
        self.title.clear()
        self.text.clear()
        self.quiet = False
        self.meta.setText("0 字")
        self.stack.setCurrentIndex(0)
        self.title.setFocus()

    def remove(self, nid):
        r = self.db.get(nid)
        box = QMessageBox(self)
        box.setWindowTitle("LanNote")
        box.setIcon(QMessageBox.Warning)
        box.setText("删掉这条？")
        box.setInformativeText(f"「{name_of(r)}」删了就找不回来。")
        ok = box.addButton("删除", QMessageBox.DestructiveRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not ok:
            return

        if nid == self.cur:
            self.tm.stop()
        else:
            self.flush()
        idx = self.lst.currentRow()
        if nid == self.cur:
            self.cur = 0
            self.quiet = True
            self.title.clear()
            self.text.clear()
            self.quiet = False
        self.db.delete(nid)
        self.reload()
        if self.lst.count():
            self.lst.setCurrentRow(min(idx, self.lst.count() - 1))
            it = self.lst.currentItem()
            self.pick(it.data(Qt.UserRole)["id"])
        else:
            self.stack.setCurrentIndex(1)

    def save(self):
        t = self.title.text().strip()
        c = self.text.toPlainText()
        if not self.cur:
            if not t and not c.strip():
                return
            self.cur = self.db.create()
            self.draft = False
        elif not t and not c.strip():
            self.tm.stop()
            self.db.delete(self.cur)
            self.cur = 0
            self.draft = True
            self.quiet = True
            if self.item is not None:
                self.lst.takeItem(self.lst.row(self.item))
                self.item = None
            self.lst.setCurrentItem(None)
            self.quiet = False
            return

        self.db.save(self.cur, t, c)
        if self.item is None:
            self.reload()
            return
        self.item.setData(Qt.UserRole, dict(self.db.get(self.cur)))
        self.lst.viewport().update()

    def flush(self):
        if self.tm.isActive():
            self.tm.stop()
            self.save()

    def touched(self):
        if self.quiet:
            return
        self.tm.start()
        s = self.title.text() + self.text.toPlainText()
        self.meta.setText(f"{len(''.join(s.split()))} 字")

    def linespace(self):
        # 行距松一点，不然一整段挤成一坨；QTextBlock 没有 setter，只能走游标
        c = QTextCursor(self.text.document())
        c.select(QTextCursor.Document)
        f = QTextBlockFormat()
        f.setLineHeight(168.0, 1)  # 1 = ProportionalHeight，PySide 这里不吃枚举
        c.mergeBlockFormat(f)

    def switched(self, cur, prev):
        if self.quiet or cur is None:
            return
        self.pick(cur.data(Qt.UserRole)["id"])

    def menu(self, pos):
        it = self.lst.itemAt(pos)
        if it is None:
            return
        n = it.data(Qt.UserRole)
        m = QMenu(self)
        for k in COLORS:
            a = m.addAction(COLORS[k]["label"])
            a.setCheckable(True)
            a.setChecked(k == n["color"])
            a.triggered.connect(lambda checked=False, key=k: self.recolor(n["id"], key))
        m.addSeparator()
        m.addAction("删除").triggered.connect(lambda: self.remove(n["id"]))
        m.exec(self.lst.viewport().mapToGlobal(pos))

    def recolor(self, nid, key):
        self.db.set_color(nid, key)
        self.reload()
        it = self.find(nid)
        if it:
            self.lst.setCurrentItem(it)

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def show_up(self):
        self.reload()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        self.flush()
        if self.keep:
            e.ignore()
            self.hide()
            return
        super().closeEvent(e)
