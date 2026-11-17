from datetime import datetime

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QPainter,
    QPalette,
    QPen,
    QShortcut,
    QTextBlockFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QInputDialog,
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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from bridge import Bridge, Editor, PeerLayer
from share import Share
from theme import COLORS, DEFAULT_COLOR, face, icon, initial, me_color, me_name

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
    def __init__(self, lst, home):
        super().__init__(lst)
        self.home = home

    def sizeHint(self, opt, idx):
        return QSize(opt.rect.width(), ROW_H)

    def badges(self, p, r, bs):
        n = min(len(bs), 3)
        x = r.right() - 6 - n * 19
        for i in range(n):
            col, nm = bs[i]
            face(p, QRect(x + i * 19, r.top() + 13, 16, 16), col, initial(nm))
        extra = len(bs) - 3
        if extra > 0:
            f = QFont(p.font())
            f.setPointSizeF(7.5)
            p.setFont(f)
            p.setPen(QColor("#8F897A"))
            p.drawText(QRect(x - 26, r.top() + 13, 24, 16),
                       Qt.AlignRight | Qt.AlignVCenter, "+%d" % extra)

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

        c = COLORS[n["color"]]
        if sel or n["color"] != DEFAULT_COLOR:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(c["swatch"]))
            p.drawRoundedRect(QRect(r.left() + 2, r.top() + 18, 3, ROW_H - 48), 1, 1)

        x = r.left() + 14
        bs = self.home.badges.get(n["uid"], [])
        w = r.width() - 26 - min(len(bs), 3) * 19 - (26 if len(bs) > 3 else 0)
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
            QRect(x, r.top() + 33, r.width() - 26, 19),
            Qt.AlignLeft | Qt.AlignVCenter,
            p.fontMetrics().elidedText(brief(n["content"]), Qt.ElideRight, r.width() - 26),
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

        if bs:
            self.badges(p, r, bs)
        p.restore()


class Me(QWidget):
    clicked = Signal()

    def __init__(self, name, color):
        super().__init__()
        self.name = name
        self.color = color
        self.live = False
        self.setFixedHeight(56)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点击改名")
        self.setFocusPolicy(Qt.NoFocus)

    def sizeHint(self):
        w = max(40, self.fontMetrics().horizontalAdvance(self.name) + 10)
        return QSize(w, 56)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        x = (self.width() - 28) // 2
        face(p, QRect(x, 1, 28, 28), self.color, initial(self.name), 9)
        if self.live:
            p.setPen(QPen(QColor("#FFFFFF"), 2))
            p.setBrush(QColor("#4CC46A"))
            p.drawEllipse(QRect(x + 18, 19, 10, 10))
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        p.setFont(f)
        p.setPen(QColor("#6F6A5C"))
        p.drawText(QRect(0, 31, self.width(), 18), Qt.AlignHCenter | Qt.AlignTop, self.name)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()


class Home(QWidget):
    def __init__(self, store):
        super().__init__()
        self.db = store
        self.keep = False
        self.cur = 0
        self.item = None
        self.quiet = False
        self.draft = False
        self.br = None
        self.layer = None
        self.badges = {}
        self.name = store.setting("name", me_name())
        self.color = store.setting("color", me_color())
        self.db.set_setting("name", self.name)
        self.db.set_setting("color", self.color)

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
        self.share = Share(self)
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
        bar.setContentsMargins(2, 0, 2, 0)
        self.me = Me(self.name, self.color)
        self.me.clicked.connect(self.rename)
        bar.addWidget(self.me)
        bar.addStretch(1)
        self.btnNew = QToolButton()
        self.btnNew.setObjectName("add")
        self.btnNew.setText("＋")
        self.btnNew.setToolTip("新建（Ctrl+N）")
        self.btnNew.setCursor(Qt.PointingHandCursor)
        self.btnNew.setFocusPolicy(Qt.NoFocus)
        self.btnNew.clicked.connect(self.new)
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
        self.lst.setItemDelegate(Row(self.lst, self))
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
        self.btnUndo.clicked.connect(self.undo)
        self.btnRedo.clicked.connect(self.redo)
        tl.addWidget(self.btnUndo)
        tl.addWidget(self.btnRedo)
        tl.addStretch(1)
        self.btnShare = self.tb("共享", "共享这条笔记")
        self.btnShare.setObjectName("share")
        self.btnShare.setFixedWidth(68)
        self.btnShare.clicked.connect(self.ask_share)
        tl.addWidget(self.btnShare)
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

        self.text = Editor()
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
        blank.setFocusPolicy(Qt.NoFocus)
        bl = QVBoxLayout(blank)
        bl.addStretch(1)
        hint = QLabel("左边选一条，或者按 Ctrl+N 新写一条")
        hint.setObjectName("hint")
        hint.setAlignment(Qt.AlignCenter)
        bl.addWidget(hint)
        bl.addStretch(1)
        self.stack.addWidget(blank)
        fade = QGraphicsOpacityEffect(blank)
        fade.setOpacity(0.55)
        blank.setGraphicsEffect(fade)

        pl.addWidget(self.stack, 1)

        self.sp.addWidget(side)
        self.sp.addWidget(pane)
        self.sp.setStretchFactor(0, 0)
        self.sp.setStretchFactor(1, 1)
        self.sp.setSizes([300, 780])

        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self.new)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.focus_search)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.flush)
        QShortcut(QKeySequence.Undo, self).activated.connect(self.undo)
        QShortcut(QKeySequence.Redo, self).activated.connect(self.redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self).activated.connect(self.redo)

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
            QToolButton#tb:disabled { color: #D6D1C4; }
            QToolButton#share {
                border: 1px solid #E6DFCF; background: #FFFFFF; color: #57523F;
                font-size: 9.5pt; padding: 0; border-radius: 7px;
            }
            QToolButton#share:hover { background: #F5F1E6; }
            QToolButton#share[on="true"] {
                background: #FDF1C9; border-color: #E7CB77; color: #6B5410;
            }
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
            self.page(1)
        self.refresh_badges()

    def page(self, i):
        self.stack.setCurrentIndex(i)
        self.btnUndo.setEnabled(i == 0)
        self.btnRedo.setEnabled(i == 0)

    def find(self, nid):
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            if it.data(Qt.UserRole)["id"] == nid:
                return it
        return None

    def note_name(self):
        return name_of(self.db.get(self.cur)) if self.cur else "未打开笔记"

    def pick(self, nid):
        if nid == self.cur:
            return
        self.flush()
        self.detach()
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
        self.page(0)
        self.attach()
        self.share.say_presence()
        self.title.setFocus()

    def new(self):
        self.search.clear()
        if self.draft and not self.title.text().strip() and not self.text.toPlainText().strip():
            self.title.setFocus()
            return
        self.flush()
        self.detach()
        self.cur = 0
        self.draft = True
        self.item = None
        self.quiet = True
        self.lst.setCurrentItem(None)
        self.title.clear()
        self.text.clear()
        self.quiet = False
        self.meta.setText("0 字")
        self.page(0)
        self.share.say_presence()
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

        if self.share.live and self.share.note["id"] == nid:
            self.share.stop()
        if nid == self.cur:
            self.tm.stop()
        else:
            self.flush()
        idx = self.lst.currentRow()
        if nid == self.cur:
            self.detach()
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
            self.page(1)

    def save(self):
        t = self.title.text().strip()
        c = self.text.toPlainText()
        if self.share.live and self.share.note["id"] == self.cur:
            c = self.share.sdoc.t()
        if not self.cur:
            if not t and not c.strip():
                return
            self.cur = self.db.create()
            self.draft = False
        elif not t and not c.strip():
            if self.share.live and self.share.note["id"] == self.cur:
                self.db.save(self.cur, t, c)
                return
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
            self.detach()
            self.page(1)
            self.share.say_presence()
            return

        self.db.save(self.cur, t, c)
        if self.share.live and self.share.note["id"] == self.cur:
            self.share.note["title"] = t
            self.share.note["color"] = self.db.get(self.cur)["color"]
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
        # QTextBlock 没有 setter，只能走游标
        c = QTextCursor(self.text.document())
        c.select(QTextCursor.Document)
        f = QTextBlockFormat()
        f.setLineHeight(168.0, 1)  # 1 = ProportionalHeight，PySide 这里不吃枚举
        c.mergeBlockFormat(f)

    def attach(self):
        self.detach()
        if not self.share.live or not self.cur:
            return
        if self.db.get(self.cur)["uid"] != self.share.note["uid"]:
            return
        self.text.setUndoRedoEnabled(False)
        self.br = Bridge(self.text, self.share.sdoc)
        self.br.tell = self.share.cur_moved
        self.layer = PeerLayer(self.text, self.share.sdoc)
        self.br.touched.connect(self.layer.refresh)
        self.share.layer = self.layer
        self.share.replay()
        self.br.render()
        self.share.cur_moved()

    def detach(self):
        if self.br:
            self.br.release()
            self.br = None
        if self.layer:
            self.text.viewport().removeEventFilter(self.layer)
            self.layer.hide()
            self.layer.setParent(None)
            self.layer.deleteLater()
            self.layer = None
        self.share.layer = None
        self.text.setExtraSelections([])

    def undo(self):
        if self.br:
            if self.br.doc.undo():
                self.br.render()
            self.touched()
            return
        self.text.undo()

    def redo(self):
        if self.br:
            if self.br.doc.redo():
                self.br.render()
            self.touched()
            return
        self.text.redo()

    def ask_share(self):
        if self.share.live:
            self.share.panel.show_panel()
            return
        self.flush()
        if not self.cur:
            QMessageBox.information(self, "LanNote", "先打开一条笔记")
            return
        self.share.panel.show_panel()

    def rename(self):
        name, ok = QInputDialog.getText(self, "改名", "你的名字（最多 5 字）",
                                        QLineEdit.Normal, self.me.name)
        name = name.strip()[:5]
        if not ok or not name:
            return
        self.rename_to(name)

    def rename_to(self, name):
        self.me.name = name
        self.me.updateGeometry()
        self.me.update()
        self.db.set_setting("name", name)
        self.share.rename()

    def share_ui(self):
        live = self.share.live
        self.btnShare.setText("共享中" if live else "共享")
        self.btnShare.setProperty("on", "true" if live else "false")
        self.btnShare.style().unpolish(self.btnShare)
        self.btnShare.style().polish(self.btnShare)
        self.me.live = live
        self.me.update()
        self.refresh_badges()

    def refresh_badges(self):
        self.badges = self.share.here() if self.share.live else {}
        self.lst.viewport().update()

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
        if self.share.live and self.share.note["id"] == nid:
            self.share.note["color"] = key
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
            self.share.panel.hide()
            if self.share.live:
                self.share.flush_session()
            e.ignore()
            self.hide()
            return
        self.share.stop()
        super().closeEvent(e)
