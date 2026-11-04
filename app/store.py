import sqlite3
import sys
import time
from pathlib import Path

from PySide6.QtCore import QStandardPaths

FIELDS = {"content", "color", "x", "y", "w", "h", "font_size", "pinned", "updated"}


def db_path():
    # 打包后 sys.executable 才是 exe 目录
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "data" / "lannote.db"


def fallback_path():
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    d = Path(base) if base else Path.home() / ".lannote"
    d.mkdir(parents=True, exist_ok=True)
    return d / "lannote.db"


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else db_path()
        try:
            self._open()
        except (sqlite3.OperationalError, OSError):
            if path:
                raise
            self.path = fallback_path()
            self._open()

    def _open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        # WAL 模式，坏处是多出 -wal/-shm 两个文件
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT 'yellow',
                x INTEGER,
                y INTEGER,
                w INTEGER,
                h INTEGER,
                font_size INTEGER NOT NULL DEFAULT 12,
                pinned INTEGER NOT NULL DEFAULT 0,
                updated REAL NOT NULL
            )
            """
        )
        self.conn.commit()

    def notes(self):
        return list(self.conn.execute("SELECT * FROM notes ORDER BY id"))

    def get(self, id):
        return self.conn.execute("SELECT * FROM notes WHERE id=?", (id,)).fetchone()

    def create(self, x, y, w, h, color, size):
        cur = self.conn.execute(
            "INSERT INTO notes (x,y,w,h,color,font_size,updated) VALUES (?,?,?,?,?,?,?)",
            (x, y, w, h, color, size, time.time()),
        )
        self.conn.commit()
        return self.get(cur.lastrowid)

    def update(self, id, **kw):
        vals = {k: v for k, v in kw.items() if k in FIELDS}
        if not vals:
            return
        vals.setdefault("updated", time.time())
        sql = ", ".join(f"{k}=?" for k in vals)
        self.conn.execute(f"UPDATE notes SET {sql} WHERE id=?", (*vals.values(), id))
        self.conn.commit()

    def delete(self, id):
        self.conn.execute("DELETE FROM notes WHERE id=?", (id,))
        self.conn.commit()

    def close(self):
        self.conn.close()
