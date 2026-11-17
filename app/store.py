import sqlite3
import sys
import time
import uuid
from pathlib import Path


def db_path():
    # 打包后 sys.executable 才是 exe 目录
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    return base / "data" / "lannote.db"


class Store:
    def __init__(self, path=None):
        p = Path(path) if path else db_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(p)
        self.conn.row_factory = sqlite3.Row
        # WAL 模式，坏处是多出 -wal/-shm 两个文件
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT 'yellow',
                updated REAL NOT NULL
            )
            """
        )
        self.conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(notes)")}
        if "title" not in cols:
            self.conn.execute("ALTER TABLE notes ADD COLUMN title TEXT NOT NULL DEFAULT ''")
        if "uid" not in cols:
            self.conn.execute("ALTER TABLE notes ADD COLUMN uid TEXT NOT NULL DEFAULT ''")
        self.conn.execute("DELETE FROM notes WHERE trim(title)='' AND trim(content)=''")
        self.conn.commit()

        rows = self.conn.execute("SELECT id FROM notes WHERE uid=''").fetchall()
        for r in rows:
            self.conn.execute("UPDATE notes SET uid=? WHERE id=?", (uuid.uuid4().hex, r["id"]))
        self.conn.commit()

    def notes(self):
        return list(self.conn.execute("SELECT * FROM notes ORDER BY updated DESC"))

    def get(self, id):
        return self.conn.execute("SELECT * FROM notes WHERE id=?", (id,)).fetchone()

    def by_uid(self, uid):
        return self.conn.execute("SELECT * FROM notes WHERE uid=?", (uid,)).fetchone()

    def create(self):
        cur = self.conn.execute("INSERT INTO notes (uid, updated) VALUES (?, ?)",
                                (uuid.uuid4().hex, time.time()))
        self.conn.commit()
        return cur.lastrowid

    def save(self, id, title, content):
        self.conn.execute(
            "UPDATE notes SET title=?, content=?, updated=? WHERE id=?",
            (title, content, time.time(), id),
        )
        self.conn.commit()

    def set_color(self, id, color):
        self.conn.execute("UPDATE notes SET color=?, updated=? WHERE id=?", (color, time.time(), id))
        self.conn.commit()

    def upsert(self, uid, title, color):
        r = self.by_uid(uid)
        if r:
            self.conn.execute("UPDATE notes SET title=?, color=?, updated=? WHERE id=?",
                              (title, color, time.time(), r["id"]))
            self.conn.commit()
            return r["id"]
        cur = self.conn.execute(
            "INSERT INTO notes (uid, title, content, color, updated) VALUES (?, ?, '', ?, ?)",
            (uid, title, color, time.time()))
        self.conn.commit()
        return cur.lastrowid

    def delete(self, id):
        self.conn.execute("DELETE FROM notes WHERE id=?", (id,))
        self.conn.commit()

    def setting(self, key, default=""):
        r = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set_setting(self, key, value):
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=?", (key, value, value))
        self.conn.commit()

    def close(self):
        self.conn.close()
