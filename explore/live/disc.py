import asyncio
import socket

from wire import (ANN_MS, ANNOUNCE, APP, BYE, DISC_PORT, PEER_TTL_MS, RID,
                  VER, now_ms, pack, unpack)


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
    return ip


class Disc:
    def __init__(self, iid, name, ws_port, on_peer, log, port=DISC_PORT):
        self.rid = RID
        self.iid = iid
        self.name = name
        self.ws_port = ws_port
        self.on_peer = on_peer
        self.log = log
        self.port = port
        self.tx = None
        self.rx = None
        self.peers = {}
        self.reply_at = {}
        self.tasks = []
        # 还没连上时发得勤一点，连上以后回到 1.5s
        self.busy = lambda: False

    def _sock(self, bind):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.bind(bind)
        s.setblocking(False)
        return s

    async def start(self):
        # 收广播用固定端口；发用一个临时口，自己发的不会绕回自己的收件箱
        self.rx = self._sock(("", self.port))
        self.tx = self._sock(("", 0))
        self.log("disc-listen 0.0.0.0:%d" % self.port)
        self.tasks = [asyncio.create_task(self._rx()),
                      asyncio.create_task(self._ann()),
                      asyncio.create_task(self._expire())]

    def payload(self, t):
        return pack(t, v=VER, app=APP, rid=self.rid, iid=self.iid,
                    name=self.name, ws=self.ws_port, ts=now_ms()).encode()

    def _cast(self, data):
        self.tx.sendto(data, ("<broadcast>", self.port))

    async def _ann(self):
        # 开局连发几个，对方正好在启动也不会漏
        d = self.payload(ANNOUNCE)
        for wait in (0, 0.15, 0.4):
            await asyncio.sleep(wait)
            self._cast(d)
        while True:
            self._cast(self.payload(ANNOUNCE))
            await asyncio.sleep((ANN_MS if self.busy() else 400) / 1000)

    async def _expire(self):
        while True:
            await asyncio.sleep(0.5)
            t = now_ms()
            for iid, p in list(self.peers.items()):
                if t - p["seen"] > PEER_TTL_MS:
                    del self.peers[iid]
                    self.log("peer-expire %s %s" % (p["name"], iid))

    async def _rx(self):
        loop = asyncio.get_running_loop()
        while True:
            data, addr = await loop.sock_recvfrom(self.rx, 4096)
            d = unpack(data)
            if not d or d.get("app") != APP or d.get("v") != VER:
                continue
            if d.get("rid") != self.rid or d.get("iid") == self.iid:
                continue
            iid = d["iid"]
            if d["t"] == BYE:
                p = self.peers.pop(iid, None)
                if p:
                    self.log("peer-bye %s %s" % (p["name"], iid))
                continue
            p = self.peers.get(iid)
            if p is None:
                p = {"iid": iid, "name": d["name"], "addr": addr[0],
                     "ws": d["ws"], "seen": now_ms()}
                self.peers[iid] = p
                self.log("peer-seen %s %s %s:%s" %
                         (p["name"], iid, p["addr"], p["ws"]))
                await self.on_peer(p)
            else:
                p["seen"] = now_ms()
                if p["ws"] != d["ws"] or p["addr"] != addr[0]:
                    p["ws"] = d["ws"]
                    p["addr"] = addr[0]
                    self.log("peer-moved %s %s -> %s:%s" %
                             (p["name"], iid, p["addr"], p["ws"]))
                    await self.on_peer(p)
            # 听到新人就立刻回一条，对方不用等下一个周期
            if now_ms() - self.reply_at.get(iid, 0) > 300:
                self.reply_at[iid] = now_ms()
                self._cast(self.payload(ANNOUNCE))

    def bye(self):
        self._cast(self.payload(BYE))
        for t in self.tasks:
            t.cancel()
