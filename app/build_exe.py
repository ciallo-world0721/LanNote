import os
import struct
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from theme import _icon_pixmap  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]


def write_icon(path):
    blobs = []
    for size in SIZES:
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        _icon_pixmap(size).save(buffer, "PNG")
        buffer.close()
        blobs.append(bytes(data.data()))

    header = struct.pack("<HHH", 0, 1, len(SIZES))
    entries = b""
    payload = b""
    offset = 6 + 16 * len(SIZES)
    for size, blob in zip(SIZES, blobs):
        dimension = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32,
                               len(blob), offset + len(payload))
        payload += blob
    path.write_bytes(header + entries + payload)


def main():
    app = QApplication([])  # noqa: F841  QPixmap 需要 QGuiApplication
    out = HERE / "build"
    out.mkdir(exist_ok=True)
    ico = out / "lannote.ico"
    write_icon(ico)
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "LanNote探索版",
        "--icon", str(ico),
        "--collect-all", "loro",
        "--distpath", str(HERE),
        "--workpath", str(out),
        "--specpath", str(out),
        str(HERE / "main.py"),
    ]
    return subprocess.run(command, cwd=HERE).returncode


if __name__ == "__main__":
    sys.exit(main())
