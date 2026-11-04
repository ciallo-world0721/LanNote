import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QStandardPaths, Qt
from PySide6.QtGui import QCursor, QFont, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from home import Home
from note import NoteWindow
from store import Store
from theme import DEFAULT_COLOR, icon

APP_NAME = "LanNote"
NEW_SIZE = (320, 320)
NEW_FONT = 12


def _log_error(t, v, tb):
    txt = "".join(traceback.format_exception(t, v, tb))
    try:
        p = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / "error.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.open("a", encoding="utf-8").write(txt + "\n")
    except OSError:
        pass
    if QApplication.instance():
        QMessageBox.critical(None, APP_NAME, f"出错了：\n\n{v}")


class Ctl(QObject):
    def __init__(self, app, store):
        super().__init__()
        self.app = app
        self.db = store
        self.wins = {}
        self.idx = 0
        self.tray = None

        self.home = Home(store)
        self.home.new_note.connect(self.new)
        self.home.open_note.connect(self.open)
        self.home.delete_note.connect(self.remove)

        self._tray()
        # 关首页不是退出，托盘还能叫回来
        self.home.keep_in_tray = self.tray is not None
        self.home.show()

    def _win(self, row):
        nid = int(row["id"])
        w = self.wins.get(nid)
        if w:
            w.show()
            w.raise_()
            w.activateWindow()
            return w
        w = NoteWindow(self.db, row)
        w.new_requested.connect(self.new)
        w.saved.connect(self._saved)
        w.closed.connect(self._closed)
        self.wins[nid] = w
        w.show()
        return w

    def open(self, nid):
        w = self.wins.get(nid)
        if w:
            w.show()
            w.raise_()
            w.activateWindow()
            w.focus()
            return
        row = self.db.get(nid)
        if row is None:
            self.home.reload()
            return
        self._win(row).focus()

    def new(self):
        s = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        a = s.availableGeometry()
        w, h = NEW_SIZE
        off = (self.idx % 6) * 26
        self.idx += 1
        x = a.center().x() - w // 2 + off
        y = a.center().y() - h // 2 + off
        row = self.db.create(x, y, w, h, DEFAULT_COLOR, NEW_FONT)
        win = self._win(row)
        win.focus()
        return win

    def remove(self, nid):
        w = self.wins.pop(nid, None)
        if w:
            w.close()
            w.deleteLater()
        self.db.delete(nid)
        self.home.reload()

    def _saved(self, nid):
        self.home.reload_later()

    def _closed(self, nid):
        w = self.wins.pop(nid, None)
        if w:
            w.deleteLater()

    def _tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.app.setQuitOnLastWindowClosed(True)
            return
        self.app.setQuitOnLastWindowClosed(False)
        self.tray = QSystemTrayIcon(icon(), self)
        self.tray.setToolTip(APP_NAME)
        m = QMenu()
        m.addAction("打开主界面").triggered.connect(self.show_home)
        m.addAction("新建便签").triggered.connect(self.new)
        m.addSeparator()
        m.addAction("退出").triggered.connect(self.quit)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(self._tray_click)
        self.tray.show()

    def _tray_click(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_home()

    def show_home(self):
        self.home.show_up()

    def quit(self):
        for w in list(self.wins.values()):
            w.close()
        self.wins.clear()
        self.home.keep_in_tray = False
        self.home.close()
        if self.tray:
            self.tray.hide()
        self.db.close()
        self.app.quit()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setWindowIcon(icon())
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setQuitOnLastWindowClosed(False)
    sys.excepthook = _log_error

    lock = QLockFile(str(Path(QStandardPaths.writableLocation(QStandardPaths.TempLocation)) / "lannote.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, APP_NAME, "LanNote 已经在运行了，看看右下角的托盘图标。")
        return 0

    store = Store()
    ctl = Ctl(app, store)
    try:
        return app.exec()
    finally:
        if ctl.tray:
            ctl.tray.hide()
        try:
            store.close()
        except Exception:
            pass
        lock.unlock()


if __name__ == "__main__":
    sys.exit(main())
