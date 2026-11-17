import queue
import subprocess
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)

from disc import lan_ip
from doc import SharedDoc
from net import NetThread
from wire import (CUR, DISC_PORT, END, HELLO, NEED, NOTE, PRESENCE, UPD,
                  b64, new_iid, now_ms, unb64)


def log(m):
    print("%8.3f share %s" % (time.time() % 100000, m), flush=True)


def net_info():
    ssid = ""
    # windowed exe 里跑 netsh 不能弹黑框；输出跟着控制台代码页走，UTF-8 和 GBK 都见过
    try:
        raw = subprocess.run(["netsh", "wlan", "show", "interfaces"],
                             capture_output=True, timeout=3,
                             creationflags=0x08000000).stdout
        try:
            out = raw.decode("utf-8")
        except UnicodeDecodeError:
            out = raw.decode("gbk", "replace")
        for line in out.splitlines():
            k, _, val = line.partition(":")
            if k.strip() == "SSID":
                ssid = val.strip()
                break
    except (OSError, subprocess.SubprocessError):
        pass
    ip = lan_ip()
    if ssid:
        return "网络：%s · 本机 %s" % (ssid, ip)
    return "网络：有线/未知 · 本机 %s" % ip


class Panel(QDialog):
    def __init__(self, share):
        super().__init__(share.win)
        self.share = share
        self.setWindowFlags(Qt.Tool | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.setModal(False)
        self.setWindowTitle("共享")
        self.setFixedWidth(336)

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 14)
        v.setSpacing(9)

        self.head = QLabel("")
        self.head.setObjectName("phead")
        self.head.setWordWrap(True)
        v.addWidget(self.head)

        self.net = QLabel("")
        self.net.setObjectName("pnet")
        self.net.setWordWrap(True)
        v.addWidget(self.net)

        self.body = QLabel("")
        self.body.setObjectName("pbody")
        self.body.setTextFormat(Qt.RichText)
        self.body.setWordWrap(True)
        v.addWidget(self.body)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        self.go = QPushButton("确认共享")
        self.cancel = QPushButton("取消")
        self.fold = QPushButton("收起")
        self.end = QPushButton("关闭共享")
        for b in (self.go, self.cancel, self.fold, self.end):
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            row.addWidget(b)
        v.addLayout(row)

        self.go.clicked.connect(self.confirm)
        self.cancel.clicked.connect(self.hide)
        self.fold.clicked.connect(self.hide)
        self.end.clicked.connect(self.share.stop)

        self.setStyleSheet(
            """
            QDialog { background: #FCFBF6; }
            QLabel#phead { color: #2E2C26; font-size: 11pt; font-weight: 600; }
            QLabel#pnet { color: #7E7868; font-size: 9pt; }
            QLabel#pbody { color: #55503F; font-size: 9.5pt; }
            QPushButton {
                border: 1px solid #E3DDCC; border-radius: 6px; padding: 5px 12px;
                background: #FFFFFF; color: #4A463C; font-size: 9.5pt;
            }
            QPushButton:hover { background: #F4F0E4; }
            QPushButton:default { background: #F6C445; border-color: #E9B62C; color: #4A3A0C; }
            QPushButton:default:hover { background: #F0BB2F; }
            """
        )

    def confirm(self):
        self.share.start()
        self.refresh()

    def show_panel(self):
        self.refresh()
        self.adjustSize()
        g = self.share.win.frameGeometry()
        self.move(g.right() - self.width() - 34, g.top() + 76)
        self.show()
        self.raise_()
        self.activateWindow()

    def reject(self):
        self.hide()

    def refresh(self):
        s = self.share
        if not s.net:
            self.head.setText("共享「%s」" % s.win.note_name())
            self.net.setText(net_info())
            self.body.hide()
            self.go.show()
            self.cancel.show()
            self.fold.hide()
            self.end.hide()
            return

        self.head.setText("共享中 ·「%s」· %s" %
                          (s.note["title"] or "无标题",
                           "发起者" if s.role == "host" else "受邀者"))
        self.body.show()
        if s.peers:
            lines = ["<span style='color:%s'>●</span> %s" % (p["color"], p["name"])
                     for p in s.peers.values()]
            self.body.setText("已连接<br>" + "<br>".join(lines) +
                             "<br><span style='color:#8F897A'>后来的人会自动加入</span>")
        else:
            self.body.setText("正在搜索…")
        self.go.hide()
        self.cancel.hide()
        self.fold.show()
        self.end.show()
        self.end.setText("关闭共享" if s.role == "host" else "退出共享")


class Share:
    def __init__(self, win):
        self.win = win
        self.inbox = queue.Queue()
        self.net = None
        self.sdoc = None
        self.note = None
        self.iid = ""
        self.role = ""
        self.host = ""
        self.started = 0
        self.peers = {}
        self.curs = {}
        self.layer = None
        self.mute = False
        self.synced = False
        self.cur_dirty = False
        self.panel = Panel(self)
        self.gone = QTimer(win)
        self.gone.setSingleShot(True)
        self.gone.setInterval(4000)
        self.gone.timeout.connect(self.finish)

        self.tm = QTimer(win)
        self.tm.timeout.connect(self.pump)
        self.tm.start(40)
        self.ctm = QTimer(win)
        self.ctm.timeout.connect(self.flush_cur)
        self.ctm.start(120)

    @property
    def live(self):
        return self.net is not None

    @property
    def name(self):
        return self.win.me.name

    @property
    def color(self):
        return self.win.me.color

    def start(self):
        if not self.win.cur:
            self.panel.hide()
            return
        self.gone.stop()
        self.note = dict(self.win.db.get(self.win.cur))
        self.iid = new_iid()
        self.started = now_ms()
        self.role = "host"
        self.host = self.iid
        self.mute = False
        self.synced = True
        self.new_doc(self.note["content"])
        self.net = NetThread(self.iid, self.name, self.inbox, log, DISC_PORT)
        self.net.start()
        self.win.attach()
        self.say_hello()
        self.say_presence()
        self.win.share_ui()
        log("start note=%s iid=%s" % (self.note["uid"][:8], self.iid))

    def stop(self):
        if not self.net:
            return
        if self.role == "host":
            self.net.send_block(END)
        self.finish()

    def finish(self):
        self.gone.stop()
        if not self.net:
            return
        self.flush_session()
        self.net.shutdown()
        self.net = None
        self.sdoc = None
        self.note = None
        self.peers.clear()
        self.curs.clear()
        self.host = ""
        self.role = ""
        self.mute = False
        self.win.detach()
        self.win.reload()
        self.win.share_ui()
        self.panel.hide()
        log("finish")

    def flush_session(self):
        if self.sdoc and self.note:
            self.win.db.save(self.note["id"], self.note["title"], self.sdoc.t())

    def new_doc(self, text):
        self.sdoc = SharedDoc()
        self.sdoc.on_update = self.post_upd
        if text:
            self.sdoc.ins(0, text)
        # 开场灌进去的正文跟 undo 无关，不清掉第一下撤销会把整篇清空
        self.sdoc.undo_mgr.clear()

    def post_upd(self, b):
        if self.net and not self.mute:
            self.net.post(UPD, data=b64(b))

    def my_note(self):
        return self.win.db.get(self.win.cur)["uid"] if self.win.cur else ""

    def say_hello(self):
        self.net.post(HELLO, iid=self.iid, name=self.name, color=self.color,
                      note=self.my_note(), role=self.role, started=self.started)

    def say_presence(self):
        if not self.net:
            return
        self.net.post(PRESENCE, name=self.name, color=self.color,
                      note=self.my_note(), role=self.role)

    def rename(self):
        self.panel.refresh()
        if self.net:
            self.say_hello()
            self.say_presence()
            self.cur_dirty = True

    def pump(self):
        while True:
            try:
                k, d = self.inbox.get_nowait()
            except queue.Empty:
                return
            if self.net:
                self.heard(k, **d)

    def heard(self, k, **d):
        if k == "up":
            self.say_hello()
            self.cur_dirty = True
        elif k == "down":
            self.peers.pop(d["iid"], None)
            self.curs.pop(d["iid"], None)
            if self.layer:
                self.layer.drop(d["iid"])
            if d["iid"] == self.host:
                log("host down, wait")
                self.gone.start()
                return
            self.win.refresh_badges()
            self.panel.refresh()
        elif k == "hello":
            self.take_hello(d)
        elif k == "presence":
            self.take_presence(d)
        elif k == "need":
            if self.role == "host":
                self.send_note(d["iid"])
        elif k == "note":
            self.take_note(d)
        elif k == "end":
            log("end from host")
            self.finish()
        elif k == "upd":
            data = unb64(d["data"])
            if self.win.br:
                self.win.br.apply_remote(data)
            else:
                self.sdoc.apply(data)
        elif k == "cur":
            self.curs[d["iid"]] = (d["cur"], d.get("sel"), d["name"], d["color"])
            if self.layer and self.peers.get(d["iid"], {}).get("note") == self.note["uid"]:
                self.layer.put(d["iid"], d["cur"], d.get("sel"), d["name"], d["color"])

    def take_hello(self, d):
        iid = d["iid"]
        if iid == self.host:
            self.gone.stop()
        p = self.peers.get(iid)
        if p is None:
            p = self.peers[iid] = {"started": 0}
        p.update(name=d["name"], color=d["color"], note=d["note"],
                 role=d["role"], started=d["started"])
        self.elect()
        if self.role == "host":
            self.send_note(iid)
        self.win.refresh_badges()
        self.panel.refresh()

    def elect(self):
        cands = [(self.started, self.iid)] if self.role == "host" else []
        for i, p in self.peers.items():
            if p["role"] == "host" and p["started"]:
                cands.append((p["started"], i))
        if not cands:
            return
        _, i = min(cands)
        if i == self.iid:
            if self.role != "host":
                self.role = "host"
                self.host = self.iid
                self.say_hello()
            return
        if self.role == "host":
            log("lose host to %s" % i)
            self.role = "guest"
            self.mute = True
            self.synced = False
            self.say_hello()
        if self.host != i:
            self.host = i
            self.synced = False
        if not self.synced:
            self.net.post(NEED, note=self.note["uid"])

    def take_presence(self, d):
        p = self.peers.get(d["iid"])
        if p is None:
            p = self.peers[d["iid"]] = {"started": 0}
        p.update(name=d["name"], color=d["color"], note=d["note"], role=d["role"])
        if d["note"] != self.note["uid"]:
            self.curs.pop(d["iid"], None)
            if self.layer:
                self.layer.drop(d["iid"])
        self.win.refresh_badges()
        self.panel.refresh()

    def send_note(self, iid):
        self.net.post_to(iid, NOTE, note=self.note["uid"], title=self.note["title"],
                         color=self.note["color"], data=b64(self.sdoc.snapshot()))

    def take_note(self, d):
        if d.get("iid") not in (None, self.host):
            return
        data = unb64(d["data"])
        if self.note and d["note"] == self.note["uid"]:
            was = self.synced
            self.mute = True
            if was:
                self.sdoc.apply(data)
            else:
                self.new_doc("")
                self.sdoc.apply(data)
                if self.win.cur == self.note["id"]:
                    self.win.attach()
            self.mute = False
            self.win.db.save(self.note["id"], self.note["title"], self.sdoc.t())
            self.synced = True
            if was and self.win.br:
                self.win.br.render()
            return
        self.mute = True
        nid = self.win.db.upsert(d["note"], d["title"], d["color"])
        self.win.reload()
        self.note = dict(self.win.db.get(nid))
        self.new_doc("")
        self.sdoc.apply(data)
        self.win.db.save(nid, self.note["title"], self.sdoc.t())
        self.mute = False
        self.synced = True
        log("join note=%s %d chars" % (d["note"][:8], len(self.sdoc.t())))
        if self.win.cur != nid:
            self.win.pick(nid)
        else:
            self.win.attach()
        self.say_presence()
        self.win.share_ui()
        self.panel.refresh()

    def here(self):
        out = {}
        for p in self.peers.values():
            if p["note"]:
                out.setdefault(p["note"], []).append((p["color"], p["name"]))
        return out

    def replay(self):
        # 切回共享笔记时把最后收到的光标补上，不然对方不动鼠标就看不见
        for iid, (cur, sel, name, color) in self.curs.items():
            if self.peers.get(iid, {}).get("note") == self.note["uid"]:
                self.layer.put(iid, cur, sel, name, color)

    def cur_moved(self):
        self.cur_dirty = True

    def flush_cur(self):
        if not self.net or not self.cur_dirty or not self.win.br:
            return
        self.cur_dirty = False
        self.net.post(CUR, cur=self.win.br.cur_payload(), sel=self.win.br.sel_payload(),
                      name=self.name, color=self.color)
