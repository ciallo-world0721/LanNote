from loro import ExportMode, LoroDoc, Side, UndoManager


class SharedDoc:
    def __init__(self):
        self.doc = LoroDoc()
        self.text = self.doc.get_text("t")
        self.on_update = lambda b: None
        # 订阅对象不存着会被回收，本地回调就断了
        self._sub = self.doc.subscribe_local_update(self._local)
        self.undo_mgr = UndoManager(self.doc)
        self.undo_mgr.set_merge_interval(700)
        self.undo_mgr.set_max_undo_steps(200)

    def _local(self, b):
        # 本地 commit 后才会走到这里，import_ 不会触发
        self.on_update(b)
        return True

    def t(self):
        return self.text.to_string()

    def ins(self, pos, s):
        self.text.insert(pos, s)
        self.doc.commit()

    def rm(self, pos, n):
        self.text.delete(pos, n)
        self.doc.commit()

    def rep(self, pos, n, s):
        self.text.splice(pos, n, s)
        self.doc.commit()

    def apply(self, data):
        self.doc.import_(data)

    def snapshot(self):
        return self.doc.export(ExportMode.Snapshot())

    def cursor(self, pos):
        return self.text.get_cursor(pos, Side.Right)

    def pos(self, cur):
        return self.doc.get_cursor_pos(cur).current.pos

    def undo(self):
        return self.undo_mgr.undo()

    def redo(self):
        return self.undo_mgr.redo()
