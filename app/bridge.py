from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit, QWidget
from loro import Cursor

from theme import face, initial
from wire import b64, unb64


class Editor(QTextEdit):
    def __init__(self):
        super().__init__()
        self.composing = False
        self.committing = False
        self.on_ime_done = lambda: None

    def inputMethodEvent(self, e):
        pre = e.preeditString()
        commit = e.commitString()
        if pre:
            self.composing = True
        if commit:
            # commit 那次 contentsChange 的 removed 连 preedit 一起算，模型里没有，只能事后 diff
            self.committing = True
        super().inputMethodEvent(e)
        if commit:
            self.committing = False
            self.composing = False
            self.on_ime_done()
        elif not pre and self.composing:
            # Esc 取消组合时只发一条空 preedit，不 commit；旗子不复位后面打的字都不同步
            self.composing = False
            self.on_ime_done()


class Bridge(QObject):
    touched = Signal()

    def __init__(self, ed, sdoc):
        super().__init__()
        self.ed = ed
        self.doc = sdoc
        self.applying = False
        self.ime_dirty = False
        self.pending = []
        self.my_cur = sdoc.cursor(ed.textCursor().position())
        self.tell = lambda: None
        ed.document().contentsChange.connect(self.on_change)
        ed.on_ime_done = self.after_ime
        ed.cursorPositionChanged.connect(self.on_cursor)

    def on_cursor(self):
        if self.applying:
            return
        self.my_cur = self.doc.cursor(self.ed.textCursor().position())
        self.tell()

    def on_change(self, pos, removed, added):
        if self.applying:
            return
        if self.ed.composing or self.ed.committing:
            self.ime_dirty = True
            return
        if not removed and not added:
            return
        txt = self.ed.toPlainText()
        new = txt[pos:pos + added]
        old = self.doc.t()
        # Qt 的 clear/程序化整段删除偶尔给出越界 pos，按控件文本重算
        if pos > len(old) or pos + removed > len(old):
            self.reconcile()
            return
        if removed and added and old[pos:pos + removed] == new:
            # 改行距/段落格式也会发一条 removed/added 相等、文本没变的信号。
            # 不挡掉的话每改一次格式就往 CRDT 里塞一个整段的删除+插入
            return
        if not removed:
            self.doc.ins(pos, new)
        elif not added:
            self.doc.rm(pos, removed)
        else:
            self.doc.rep(pos, removed, new)
        self.my_cur = self.doc.cursor(pos + added)
        self.tell()
        self.touched.emit()

    def after_ime(self):
        if self.ime_dirty:
            self.ime_dirty = False
            self.reconcile()
        if self.pending:
            data = self.pending
            self.pending = []
            for b in data:
                self.doc.apply(b)
            self.render()
        self.touched.emit()

    def _diff(self, a, b):
        n = min(len(a), len(b))
        i = 0
        while i < n and a[i] == b[i]:
            i += 1
        j = 0
        while j < n - i and a[len(a) - 1 - j] == b[len(b) - 1 - j]:
            j += 1
        return i, a[i:len(a) - j], b[i:len(b) - j]

    def reconcile(self):
        i, old, new = self._diff(self.doc.t(), self.ed.toPlainText())
        if not old and not new:
            return
        self.doc.rep(i, len(old), new)
        self.my_cur = self.doc.cursor(self.ed.textCursor().position())

    def apply_remote(self, data):
        if self.ed.composing or self.ed.committing:
            self.pending.append(data)
            return
        self.doc.apply(data)
        self.render()
        self.touched.emit()

    def render(self):
        ed = self.ed
        vsb = ed.verticalScrollBar()
        cur = ed.textCursor()
        before = ed.cursorRect(cur)
        vis = 0 <= before.top() < ed.viewport().height()
        top = ed.cursorForPosition(QPoint(0, 0))
        top_before = ed.cursorRect(top)
        sel = cur if cur.hasSelection() else None

        self.applying = True
        try:
            self.sync_widget()
            try:
                p = self.doc.pos(self.my_cur)
            except BaseException:
                p = ed.textCursor().position()
            c = ed.textCursor()
            if sel:
                # 选中的时候来远端更新，别把选区弄丢
                c.setPosition(sel.anchor())
                c.setPosition(sel.position(), QTextCursor.KeepAnchor)
            else:
                c.setPosition(p)
            ed.setTextCursor(c)
        finally:
            self.applying = False

        # 用文档坐标算：setTextCursor 自己会把滚动条挪一下，拿视口坐标会算两遍
        if vis:
            y = ed.cursorRect(ed.textCursor()).top() + vsb.value() - before.top()
        else:
            y = ed.cursorRect(top).top() + vsb.value() - top_before.top()
        vsb.setValue(y)
        ed.viewport().update()

    def sync_widget(self):
        i, old, new = self._diff(self.ed.toPlainText(), self.doc.t())
        if not old and not new:
            return
        doc = self.ed.document()
        box = QTextCursor(doc)
        box.beginEditBlock()
        try:
            if old:
                c = QTextCursor(doc)
                c.setPosition(i + len(old))
                c.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(old))
                c.removeSelectedText()
            if new:
                c = QTextCursor(doc)
                c.setPosition(i)
                c.insertText(new)
        finally:
            box.endEditBlock()

    def sel_payload(self):
        c = self.ed.textCursor()
        if not c.hasSelection():
            return None
        return b64(self.doc.cursor(c.anchor()).encode())

    def cur_payload(self):
        return b64(self.my_cur.encode())

    def release(self):
        self.ed.document().contentsChange.disconnect(self.on_change)
        self.ed.cursorPositionChanged.disconnect(self.on_cursor)
        self.ed.on_ime_done = lambda: None
        self.ed.setUndoRedoEnabled(True)
        self.ed.document().clearUndoRedoStacks()


class PeerLayer(QWidget):
    def __init__(self, ed, sdoc):
        super().__init__(ed.viewport())
        self.ed = ed
        self.doc = sdoc
        self.peers = {}
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(ed.viewport().rect())
        # 父窗口已经显示时再 new 出来的子控件不会自动显示
        self.show()
        ed.viewport().installEventFilter(self)
        ed.verticalScrollBar().valueChanged.connect(self.update)
        ed.horizontalScrollBar().valueChanged.connect(self.update)

    def eventFilter(self, o, e):
        if o is self.ed.viewport() and e.type() in (QEvent.Resize, QEvent.Paint):
            self.setGeometry(self.ed.viewport().rect())
        return False

    def put(self, iid, cur, sel, name, color):
        try:
            c = Cursor.decode(unb64(cur))
            s = Cursor.decode(unb64(sel)) if sel else None
        except BaseException:
            # 对方刚换过 doc 时可能收到上一代的 cursor，解不出来就等下一包
            return
        self.peers[iid] = {"cur": c, "sel": s, "name": name, "color": QColor(color)}
        self.refresh()

    def drop(self, iid):
        self.peers.pop(iid, None)
        self.refresh()

    def _cur(self, pos):
        c = QTextCursor(self.ed.document())
        c.setPosition(pos)
        return c

    def refresh(self):
        out = []
        for p in self.peers.values():
            try:
                pos = self.doc.pos(p["cur"])
                a = self.doc.pos(p["sel"]) if p["sel"] else pos
            except BaseException:
                continue
            if a != pos:
                c = self._cur(min(a, pos))
                c.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, abs(pos - a))
                sel = QTextEdit.ExtraSelection()
                sel.cursor = c
                sel.format = QTextCharFormat()
                col = QColor(p["color"])
                col.setAlpha(40)
                sel.format.setBackground(col)
                out.append(sel)
        self.ed.setExtraSelections(out)
        self.update()

    def paintEvent(self, e):
        if not self.peers:
            return
        h = self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for peer in self.peers.values():
            try:
                pos = self.doc.pos(peer["cur"])
            except BaseException:
                continue
            r = self.ed.cursorRect(self._cur(pos))
            if r.top() < -18 or r.top() > h:
                continue
            face(p, QRect(r.left(), r.top() + (r.height() - 16) // 2, 16, 16),
                 peer["color"], initial(peer["name"]))
