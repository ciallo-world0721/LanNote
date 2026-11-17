import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = [sys.executable, os.path.abspath(__file__), "--bot", "--title", "共享冒烟"]


def spawn(name, text, db, die=False):
    cmd = BASE + ["--name", name, "--text", text, "--db", db]
    if die:
        cmd.append("--die")
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", cwd=HERE)


def bot(a):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, HERE)

    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QTextCursor
    from PySide6.QtWidgets import QApplication

    from mainwin import Home
    from store import Store

    app = QApplication([])
    st = Store(a.db)
    st.set_setting("name", a.name)
    st.set_setting("color", "#3F7BD6" if a.name == "A" else "#D08A2E")
    h = Home(st)
    h.show()
    h.new()
    h.title.setText(a.title)
    h.text.setPlainText(a.text)
    h.flush()

    res = {"name": a.name, "role": "", "peers": 0, "note": "", "text": "",
           "db": "", "live": None, "fold_live": None}

    def share():
        h.ask_share()
        h.share.panel.confirm()

    def fold():
        h.share.panel.fold.click()
        res["fold_live"] = h.share.live

    def append():
        h.text.moveCursor(QTextCursor.End)
        h.text.insertPlainText("A后半段")

    def prepend():
        c = h.text.textCursor()
        c.setPosition(0)
        h.text.setTextCursor(c)
        h.text.insertPlainText("B插一句")

    def snap():
        if h.share.live:
            res["role"] = h.share.role
            res["peers"] = len(h.share.peers)
            res["note"] = h.share.note["uid"]
            res["text"] = h.share.sdoc.t()

    def end_share():
        h.share.panel.show_panel()
        h.share.panel.end.click()

    def collect():
        res["live"] = h.share.live
        if res["note"]:
            res["db"] = st.by_uid(res["note"])["content"]
        print("RESULT " + json.dumps(res, ensure_ascii=False), flush=True)
        app.quit()

    if a.name == "A":
        QTimer.singleShot(0, share)
        QTimer.singleShot(2000, fold)
        QTimer.singleShot(3000, append)
        QTimer.singleShot(7000, snap)
        if a.die:
            # 模拟发起者直接掉线：进程不打招呼就没了
            QTimer.singleShot(8500, lambda: os._exit(0))
        else:
            QTimer.singleShot(9000, end_share)
            QTimer.singleShot(11000, collect)
    else:
        QTimer.singleShot(0, share)
        QTimer.singleShot(3000, prepend)
        QTimer.singleShot(7000, snap)
        QTimer.singleShot(11500, collect)
    return app.exec()


def run(die):
    tmp = tempfile.mkdtemp(prefix="lannote-net-")
    a = spawn("A", "A的正文", os.path.join(tmp, "A.db"), die)
    time.sleep(1.5)
    b = spawn("B", "B自己的笔记", os.path.join(tmp, "B.db"))
    outs = []
    for p in (a, b):
        out, _ = p.communicate(timeout=60)
        outs.append(out)

    res = {}
    for out in outs:
        for line in out.splitlines():
            if line.startswith("RESULT "):
                d = json.loads(line[7:])
                res[d["name"]] = d

    print("---- A 日志")
    for line in outs[0].splitlines():
        if " share " in line or "hs-" in line or "connected" in line:
            print("  " + line)
    print("---- B 日志")
    for line in outs[1].splitlines():
        if " share " in line or "hs-" in line or "connected" in line:
            print("  " + line)
    print("---- 结果")
    for n in ("A", "B"):
        d = res.get(n, {})
        print("  %s role=%s peers=%s note=%s live=%s 字符=%d" %
              (n, d.get("role"), d.get("peers"), d.get("note", "")[:8],
               d.get("live"), len(d.get("text", ""))))
    return res, outs


def report(title, checks, outs):
    print("---- " + title)
    bad = 0
    for name, good in checks:
        print(("PASS " if good else "FAIL ") + name)
        bad += 0 if good else 1
    if bad:
        print("---- 原文")
        for out in outs:
            print(out)
    print(title + ":", "PASS" if not bad else "FAIL")
    return bad


def main():
    bad = 0

    res, outs = run(die=False)
    a = res.get("A", {})
    b = res.get("B", {})
    bad += report("A 关共享", [
        ("两进程都连上", a.get("peers") == 1 and b.get("peers") == 1),
        ("B 当受邀者加入", b.get("role") == "guest"),
        ("B 打开的 uid 是 A 那条", a.get("note") and a.get("note") == b.get("note")),
        ("收起面板后共享没停", a.get("fold_live") is True),
        ("正文双向收敛", a.get("text") == b.get("text") != ""),
        ("A 关共享后两边都退出", a.get("live") is False and b.get("live") is False),
        ("退出后各自落库且一致", a.get("db") == b.get("db") == a.get("text")),
        ("三处改动都在", all(s in a.get("db", "") for s in ("A的正文", "B插一句", "A后半段"))),
    ], outs)

    res, outs = run(die=True)
    b = res.get("B", {})
    bad += report("A 掉线", [
        ("B 连上过", b.get("peers") == 1),
        ("A 没了以后 B 结束会话", b.get("live") is False),
        ("B 保留了双方正文", all(s in b.get("db", "") for s in ("A的正文", "B插一句"))),
    ], outs)

    return 1 if bad else 0


if __name__ == "__main__":
    if "--bot" in sys.argv:
        ap = argparse.ArgumentParser()
        ap.add_argument("--bot", action="store_true")
        ap.add_argument("--name", required=True)
        ap.add_argument("--db", required=True)
        ap.add_argument("--title", default="共享冒烟")
        ap.add_argument("--text", default="")
        ap.add_argument("--die", action="store_true")
        sys.exit(bot(ap.parse_args()))
    sys.exit(main())
