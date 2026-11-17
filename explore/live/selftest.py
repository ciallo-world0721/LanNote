import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from doc import SharedDoc
from mainwin import Home
from store import Store, db_path
from theme import initial
from wire import b64

FAIL = []


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("  " + str(extra) if extra else ""))
    if not cond:
        FAIL.append(name)


def pump(app):
    app.processEvents()
    QTest.qWait(40)
    app.processEvents()


def legacy_db(path):
    # 浮窗版没有 title 列，迁移要真的走 ALTER
    c = sqlite3.connect(path)
    c.execute(
        "CREATE TABLE notes (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " content TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT 'yellow', updated REAL NOT NULL)")
    c.execute("INSERT INTO notes (content, updated) VALUES ('正文一', 1.0)")
    c.execute("INSERT INTO notes (content, updated) VALUES ('正文二', 2.0)")
    c.commit()
    c.close()


def snap(uid, text):
    d = SharedDoc()
    d.ins(0, text)
    return d.snapshot()


def main():
    app = QApplication([])
    tmp = Path(tempfile.mkdtemp(prefix="lannote-selftest-"))
    ok("源码数据目录不落到主线库", db_path().parent == Path(__file__).resolve().parent / "data", db_path())
    ok("头像取名字首字", initial("郑日新") == "郑" and initial("Alice") == "A")

    old = tmp / "old.db"
    legacy_db(old)
    st = Store(old)
    rows = st.notes()
    uids = [r["uid"] for r in rows]
    ok("旧库迁移：两行都在", len(rows) == 2, [r["title"] for r in rows])
    ok("旧库迁移：逐行生成 32 位 uid", all(len(u) == 32 for u in uids) and len(set(uids)) == 2, uids)
    ok("旧库迁移：补出 title 列", "title" in {r[1] for r in st.conn.execute("PRAGMA table_info(notes)")})
    ok("旧库迁移：正文没动", sorted(r["content"] for r in rows) == ["正文一", "正文二"])

    st.set_setting("name", "阿郑")
    st.set_setting("color", "#3F7BD6")
    h = Home(st)
    h.show()
    pump(app)

    ok("身份：左上角是名字不是「全部」", h.me.name == "阿郑" and h.me.isVisible())
    ok("身份：头像下面留了名字的位置", h.me.height() >= 50, h.me.height())
    ok("空态页带淡出", h.stack.widget(1).graphicsEffect() is not None)

    h.lst.setCurrentRow(0)
    pump(app)
    first = h.cur
    ok("首行打开", first and h.stack.currentIndex() == 0)

    h.ask_share()
    pn = h.share.panel
    ok("共享面板是非模态 Qt.Tool",
       bool(pn.windowFlags() & Qt.Tool) and not pn.isModal())
    ok("面板第一步显示网络", pn.net.text().startswith("网络："), pn.net.text())
    pn.confirm()
    pump(app)
    ok("确认共享后是发起者", h.share.live and h.share.role == "host", h.share.role)
    ok("顶栏变成「共享中」", h.btnShare.text() == "共享中")
    ok("头像开了绿点", h.me.live)
    ok("共享笔记绑上 Bridge/PeerLayer", h.br is not None and h.layer is not None)

    host_uid = "a" * 32
    body = "发起者正文\n第二段"
    h.share.role = "guest"
    h.share.synced = False
    h.share.take_note({"note": host_uid, "title": "发起者的标题", "color": "mint",
                       "data": b64(snap(host_uid, body))})
    pump(app)
    got = st.by_uid(host_uid)
    ok("受邀者本地没有该 uid → 插一条", got is not None and len(st.notes()) == 3, len(st.notes()))
    ok("插入的是发起者的正文", got["content"] == body and h.text.toPlainText() == body, got["content"])
    ok("自动打开同一条", h.cur == got["id"] and h.share.note["uid"] == host_uid)
    ok("打开的共享笔记已绑定", h.br is not None)

    h.share.synced = False
    body2 = "替换后的正文"
    h.share.take_note({"note": host_uid, "title": "发起者的标题", "color": "mint",
                       "data": b64(snap(host_uid, body2))})
    pump(app)
    ok("同 uid 用发起者快照替换正文",
       st.by_uid(host_uid)["content"] == body2 and len(st.notes()) == 3, st.by_uid(host_uid)["content"])

    uid = h.share.note["uid"]
    h.share.heard("hello", iid="bbbb1111", name="阿柯", color="#D08A2E",
                  note=uid, role="guest", started=1)
    ok("badge：别人在这条笔记里", h.badges.get(uid) == [("#D08A2E", "阿柯")], h.badges)
    h.share.heard("presence", iid="bbbb1111", name="阿柯", color="#D08A2E", note="", role="guest")
    ok("badge：别人切走就消失", not h.badges.get(uid), h.badges)

    for i, nm in enumerate(("阿柯", "小林", "阿郑", "小周")):
        h.share.heard("presence", iid="p%d" % i, name=nm, color="#4C9AA8", note=uid, role="guest")
    ok("badge：4 个人都在，delegate 取前 3 加 +1", len(h.badges[uid]) == 4, h.badges[uid])
    ok("带 badge 重绘列表不崩", not h.lst.grab().isNull())
    h.share.heard("cur", iid="p0", cur=b64(h.share.sdoc.cursor(3).encode()),
                  sel=None, name="阿柯", color="#4C9AA8")
    ok("收到对方光标 → 编辑区有标记", "p0" in h.layer.peers)

    pn.show_panel()
    ok("共享中再点按钮能重开面板", pn.isVisible())
    pn.fold.click()
    ok("收起：面板隐藏、共享还在",
       (not pn.isVisible()) and h.share.live and h.btnShare.text() == "共享中")
    pn.show_panel()
    pn.reject()
    ok("X/关闭：只隐藏不算停", (not pn.isVisible()) and h.share.live)
    h.text.insertPlainText("收起后打字")
    pump(app)
    ok("收起后照样编辑进 doc", "收起后打字" in h.share.sdoc.t(), h.share.sdoc.t()[:12])

    other = [r["id"] for r in st.notes() if r["id"] != h.cur][0]
    h.pick(other)
    pump(app)
    ok("切走共享笔记：解绑编辑器", h.br is None and h.layer is None)
    ok("切走后面板/按钮仍显示共享中", h.share.live and h.btnShare.text() == "共享中")
    ok("切走后那行还挂着对方头像", len(h.badges.get(uid, [])) == 4, h.badges.get(uid))
    h.pick(h.share.note["id"])
    pump(app)
    ok("切回共享笔记：重新绑定", h.br is not None and h.layer is not None)
    ok("切回来对方光标还在", "p0" in h.layer.peers)

    nid = h.share.note["id"]
    doc_text = h.share.sdoc.t()
    pn.show_panel()
    ok("受邀者按钮叫「退出共享」", pn.end.text() == "退出共享", pn.end.text())
    pn.end.click()
    pump(app)
    ok("退出后共享结束", (not h.share.live) and h.btnShare.text() == "共享" and not pn.isVisible())
    ok("退出后正文落库", st.get(nid)["content"] == doc_text, st.get(nid)["content"][:12])
    ok("退出后解绑", h.br is None and h.layer is None and not h.me.live)

    nid2 = h.cur
    h.share.start()
    pump(app)
    h.title.clear()
    h.text.selectAll()
    h.text.textCursor().removeSelectedText()
    h.flush()
    pump(app)
    ok("共享中清空正文不删这一行", st.get(nid2) is not None and h.share.live,
       (st.get(nid2) is not None, h.share.live))
    h.title.setText("恢复标题")
    h.text.setPlainText("恢复正文")
    h.flush()
    h.share.stop()
    pump(app)

    h.share.start()
    pump(app)
    new_uid = "e" * 32
    h.share.role = "guest"
    h.share.synced = True
    h.share.heard("hello", iid="aaaa0000", name="A", color="#3F7BD6",
                  note=h.share.note["uid"], role="host", started=h.share.started - 1000)
    h.share.take_note({"iid": "aaaa0000", "note": new_uid, "title": "新 host",
                       "color": "sky", "data": b64(snap(new_uid, "新 host 正文"))})
    pump(app)
    ok("host 换了以后改投到新笔记", h.share.note["uid"] == new_uid and
       st.by_uid(new_uid)["content"] == "新 host 正文")
    h.share.stop()
    pump(app)

    h.share.start()
    pump(app)
    h.share.heard("hello", iid="cccc2222", name="小林", color="#4F9A6A",
                  note=h.share.note["uid"], role="host", started=h.share.started - 5000)
    ok("同时点共享：started 早的当 host，自己降为受邀者",
       h.share.role == "guest" and h.share.host == "cccc2222", (h.share.role, h.share.host))
    h.share.stop()
    pump(app)

    h.share.start()
    pump(app)
    h.share.heard("hello", iid="dddd3333", name="小周", color="#B85C7E",
                  note=h.share.note["uid"], role="host", started=h.share.started + 5000)
    ok("后点共享的抢不走 host", h.share.role == "host" and h.share.host == h.share.iid)
    h.share.stop()
    pump(app)

    ok("会话全停掉", not h.share.live and not h.me.live)

    h.share.start()
    pump(app)
    try:
        h.share.layer.put("bad", b64(b"\x00\x01"), None, "X", "#000000")
        bad = "bad" not in h.share.layer.peers
    except BaseException:
        bad = False
    ok("坏 cursor 不会打断编辑区", bad)
    h.keep = True
    h.close()
    ok("关到托盘把共享面板一起收走", not h.share.panel.isVisible())
    h.show()
    h.keep = False
    h.share.stop()
    pump(app)

    h.rename_to("阿柯")
    ok("改名落到 settings 表", st.setting("name") == "阿柯" and h.me.name == "阿柯")
    st2 = Store(str(old))
    h2 = Home(st2)
    ok("重开还是那个名字", h2.me.name == "阿柯")
    h2.close()
    st2.close()

    h.close()
    st.close()
    print()
    print("失败", len(FAIL), FAIL if FAIL else "")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
