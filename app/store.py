import sqlite3
import sys
import time
from pathlib import Path


def db_path():
    # 打包后 sys.executable 才是 exe 目录
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "data" / "lannote.db"


class Store:
    def __init__(self):
        p = db_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(p)
        self.conn.row_factory = sqlite3.Row
        # WAL 模式，坏处是多出 -wal/-shm 两个文件
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT 'yellow',
                updated REAL NOT NULL
            )
            """
        )
        # 旧库是浮窗版的，多出来的 x/y/w/h 留着不管，缺 title 就补上
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(notes)")}
        if "title" not in cols:
            self.conn.execute("ALTER TABLE notes ADD COLUMN title TEXT NOT NULL DEFAULT ''")
        self.conn.execute("DELETE FROM notes WHERE trim(title)='' AND trim(content)=''")
        self.conn.commit()

    def notes(self):
        return list(self.conn.execute("SELECT * FROM notes ORDER BY updated DESC"))

    def get(self, id):
        return self.conn.execute("SELECT * FROM notes WHERE id=?", (id,)).fetchone()

    def create(self):
        cur = self.conn.execute("INSERT INTO notes (updated) VALUES (?)", (time.time(),))
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

    def delete(self, id):
        self.conn.execute("DELETE FROM notes WHERE id=?", (id,))
        self.conn.commit()

    def close(self):
        self.conn.close()
