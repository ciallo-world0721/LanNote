import argparse
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QStandardPaths
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from mainwin import Home
from store import Store
from theme import PEERS, icon

APP_NAME = "LanNote"


def logerr(t, v, tb):
    p = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / "error.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.open("a", encoding="utf-8").write("".join(traceback.format_exception(t, v, tb)) + "\n")
    QMessageBox.critical(None, APP_NAME, f"出错了：\n\n{v}")


class Ctl(QObject):
    def __init__(self, app, store):
        super().__init__()
        self.app = app
        self.tray = None

        self.home = Home(store)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(icon(), self)
            self.tray.setToolTip(APP_NAME)
            m = QMenu()
            m.addAction("打开主界面").triggered.connect(self.home.show_up)
            m.addAction("新建笔记").triggered.connect(self.new)
            m.addSeparator()
            m.addAction("退出").triggered.connect(self.quit)
            self.tray.setContextMenu(m)
            self.tray.activated.connect(self.clicked)
            self.tray.show()
            app.setQuitOnLastWindowClosed(False)
        self.home.keep = self.tray is not None
        self.home.show()

    def clicked(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.home.show_up()

    def new(self):
        self.home.show_up()
        self.home.new()

    def quit(self):
        self.home.keep = False
        self.home.close()
        if self.tray:
            self.tray.hide()
        self.app.quit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name")
    ap.add_argument("--db")
    ap.add_argument("--share", action="store_true")
    a = ap.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setWindowIcon(icon())
    app.setFont(QFont("Microsoft YaHei UI", 9))
    sys.excepthook = logerr

    lock = None
    if not a.db:
        lock = QLockFile(str(Path(QStandardPaths.writableLocation(QStandardPaths.TempLocation))
                             / "lannote-live.lock"))
        if not lock.tryLock(100):
            QMessageBox.information(None, APP_NAME, "LanNote 已经在跑了，看托盘。")
            return 0

    store = Store(a.db)
    if a.name and a.name.strip():
        name = a.name.strip()[:5]
        store.set_setting("name", name)
        if not store.setting("color"):
            store.set_setting("color", PEERS[sum(map(ord, name)) % len(PEERS)])

    ctl = Ctl(app, store)  # 得留引用，不然托盘被回收
    if a.share and ctl.home.cur:
        ctl.home.share.panel.show_panel()
        ctl.home.share.panel.confirm()
    rc = app.exec()
    store.close()
    if lock:
        lock.unlock()
    return rc


if __name__ == "__main__":
    sys.exit(main())
