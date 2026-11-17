import base64
import hashlib
import json
import os
import time

APP = "lannote"
VER = 1

DISC_PORT = 47821

ANNOUNCE = "ANNOUNCE"
BYE = "BYE"
HS_REQ = "HS_REQ"
HS_OK = "HS_OK"
HS_NO = "HS_NO"
PING = "PING"
PONG = "PONG"
CUR = "CUR"
UPD = "UPD"
HELLO = "HELLO"
PRESENCE = "PRESENCE"
NEED = "NEED"
NOTE = "NOTE"
END = "END"

PING_MS = 3000
DEAD_MS = 10000
ANN_MS = 1500
PEER_TTL_MS = 5000


RID = hashlib.sha256(b"lannote|lannote-share").hexdigest()[:16]


def now_ms():
    return int(time.time() * 1000)


def pack(t, **kw):
    kw["t"] = t
    return json.dumps(kw, ensure_ascii=False, separators=(",", ":"))


def unpack(s):
    try:
        d = json.loads(s)
    except ValueError:
        return None
    if not isinstance(d, dict) or "t" not in d:
        return None
    return d


def b64(b):
    return base64.b64encode(b).decode()


def unb64(s):
    return base64.b64decode(s)


def new_iid():
    return os.urandom(4).hex()
