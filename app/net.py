import asyncio

from PySide6.QtCore import QThread

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from wire import (CUR, DEAD_MS, END, HELLO, HS_NO, HS_OK, HS_REQ, NEED, NOTE,
                  PING, PING_MS, PONG, PRESENCE, RID, UPD, VER, now_ms,
                  pack, unpack)

ST_DISC = "DISCOVERED"
ST_HS = "HANDSHAKE_SENT"
ST_ON = "CONNECTED"
ST_OFF = "CLOSED"

MSG = (CUR, UPD, HELLO, PRESENCE, NEED, NOTE, END)


class Link:
    def __init__(self, net, p):
        self.net = net
        self.p = p
        self.iid = p["iid"]
        self.state = ST_DISC
        self.ws = None
        self.last_rx = now_ms()
        self.why = ""

    async def dial(self):
        if self.state in (ST_HS, ST_ON):
            return
        self.state = ST_HS
        url = "ws://%s:%d/" % (self.p["addr"], self.p["ws"])
        self.net.log("hs-send %s %s" % (self.p["name"], self.iid))
        ws = None
        try:
            ws = await asyncio.wait_for(connect(url, open_timeout=2,
                                                ping_interval=None,
                                                max_size=16 << 20), 3)
            await ws.send(pack(HS_REQ, v=VER, rid=self.net.rid,
                               iid=self.net.iid, name=self.net.name))
            d = unpack(await asyncio.wait_for(ws.recv(), 3))
            if d["t"] != HS_OK:
                raise RuntimeError("hs-reject %s" % d.get("why"))
            self.p["name"] = d["name"]
            self._up(ws, out=True)
        except asyncio.TimeoutError:
            self.state = ST_OFF
            self.why = "hs-timeout"
            self.net.log("hs-timeout %s" % self.iid)
            self.net.retry(self.iid)
        except Exception as e:
            self.state = ST_OFF
            self.why = str(e)[:80]
            self.net.log("hs-fail %s %s" % (self.iid, self.why))
            self.net.retry(self.iid)
        finally:
            if ws is not None and self.ws is None:
                await ws.close()

    async def accept(self, ws, d):
        self.p["name"] = d["name"]
        self._up(ws, out=False, spawn=False)
        # handler 一返回 websockets 就关连接，所以这里得一直挂着
        await self._run(ws)

    def _up(self, ws, out, spawn=True):
        self.ws = ws
        self.state = ST_ON
        self.last_rx = now_ms()
        self.net.log("connected %s %s dir=%s" % (self.p["name"], self.iid,
                                                 "out" if out else "in"))
        self.net.emit("up", iid=self.iid, name=self.p["name"])
        if spawn:
            asyncio.create_task(self._run(ws))

    async def _run(self, ws):
        asyncio.create_task(self._ping(ws))
        try:
            async for raw in ws:
                d = unpack(raw)
                if not d:
                    continue
                self.last_rx = now_ms()
                await self.net.on_msg(self, d)
        except ConnectionClosed as e:
            self.why = "closed %s" % (e.rcvd.code if e.rcvd else "?")
        except Exception as e:
            self.why = str(e)[:80]
        self.ws = None
        self.state = ST_OFF
        self.net.log("closed %s %s" % (self.iid, self.why or "eof"))
        self.net.emit("down", iid=self.iid, name=self.p["name"])
        self.net.retry(self.iid)

    async def _ping(self, ws):
        while self.state == ST_ON:
            await asyncio.sleep(PING_MS / 1000)
            if self.state != ST_ON:
                return
            if now_ms() - self.last_rx > DEAD_MS:
                self.why = "ping-timeout"
                await ws.close()
                return
            await ws.send(pack(PING, ts=now_ms()))

    async def send(self, t, **kw):
        if self.state != ST_ON:
            return
        await self.ws.send(pack(t, **kw))

    async def drop(self, why):
        self.why = why
        if self.ws:
            await self.ws.close()


class Net:
    def __init__(self, iid, name, emit, log):
        self.rid = RID
        self.iid = iid
        self.name = name
        self.emit = emit
        self.log = log
        self.links = {}
        self.disc = None
        self._retry_at = {}

    async def start(self):
        self._server = await serve(self._handler, "0.0.0.0", 0,
                                   ping_interval=None, max_size=16 << 20)
        return self._server.sockets[0].getsockname()[1]

    async def _handler(self, ws):
        d = unpack(await asyncio.wait_for(ws.recv(), 5))
        if d is None or d["t"] != HS_REQ or d.get("rid") != self.rid:
            await ws.send(pack(HS_NO, v=VER, why="room"))
            self.log("hs-reject room")
            await ws.close()
            return
        iid = d["iid"]
        old = self.links.get(iid)
        if old and old.state == ST_ON and self.iid < iid:
            await ws.send(pack(HS_NO, v=VER, why="dup"))
            self.log("hs-dup %s" % iid)
            await ws.close()
            return
        if old is None:
            old = Link(self, {"iid": iid, "name": d["name"],
                              "addr": ws.remote_address[0], "ws": 0})
            self.links[iid] = old
        await ws.send(pack(HS_OK, v=VER, rid=self.rid, iid=self.iid, name=self.name))
        await old.accept(ws, d)

    async def on_peer(self, p):
        l = self.links.get(p["iid"])
        if l and l.state in (ST_ON, ST_HS):
            l.p = p
            return
        if l is None:
            l = Link(self, p)
            self.links[p["iid"]] = l
        else:
            l.p = p
            l.state = ST_DISC
        if self.iid > p["iid"]:
            await l.dial()

    def retry(self, iid):
        t = now_ms()
        if t < self._retry_at.get(iid, 0):
            return
        if iid not in self.disc.peers:
            self.log("give-up %s" % iid)
            return
        self._retry_at[iid] = t + 1500
        l = self.links[iid]

        async def go():
            await asyncio.sleep(1.2)
            if l.state == ST_OFF and self.iid > iid:
                self.log("retry %s" % iid)
                await l.dial()

        asyncio.create_task(go())

    def peers(self):
        return [l.p for l in self.links.values() if l.state == ST_ON]

    async def send_all(self, t, **kw):
        for l in list(self.links.values()):
            if l.state == ST_ON:
                await l.send(t, **kw)

    async def send_to(self, iid, t, **kw):
        l = self.links.get(iid)
        if l and l.state == ST_ON:
            await l.send(t, **kw)

    async def on_msg(self, link, d):
        t = d["t"]
        if t == PING:
            await link.send(PONG, ts=d["ts"])
            return
        if t == PONG:
            return
        if t in MSG:
            body = {k: v for k, v in d.items() if k not in ("t", "iid")}
            self.emit(t.lower(), iid=link.iid, **body)
            return

    async def stop(self):
        for l in self.links.values():
            await l.drop("bye")
        self._server.close()


class NetThread(QThread):
    def __init__(self, iid, name, inbox, log, disc_port):
        super().__init__()
        self.iid = iid
        self.name = name
        self.inbox = inbox
        self.log = log
        self.disc_port = disc_port
        self.loop = None
        self.net = None
        self.disc = None

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._boot())
            self.loop.run_forever()
        finally:
            self.loop.close()

    async def _boot(self):
        self.net = Net(self.iid, self.name,
                       lambda k, **kw: self.inbox.put((k, kw)), self.log)
        port = await self.net.start()
        from disc import Disc
        self.disc = Disc(self.iid, self.name, port, self.net.on_peer,
                         self.log, self.disc_port)
        self.net.disc = self.disc
        self.disc.busy = lambda: bool(self.net.peers())
        await self.disc.start()
        self.log("listen 0.0.0.0:%d" % port)

    def post(self, t, **kw):
        if not self.loop:
            return
        self.loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self.net.send_all(t, **kw)))

    def post_to(self, iid, t, **kw):
        if not self.loop:
            return
        self.loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self.net.send_to(iid, t, **kw)))

    def send_block(self, t, **kw):
        if not self.loop:
            return

        async def go():
            await self.net.send_all(t, **kw)

        try:
            asyncio.run_coroutine_threadsafe(go(), self.loop).result(1)
        except Exception as e:
            self.log("end-fail %s" % e)

    def shutdown(self):
        if not self.loop:
            return
        async def go():
            self.disc.bye()
            await self.net.stop()
        fut = asyncio.run_coroutine_threadsafe(go(), self.loop)
        try:
            fut.result(2)
        except Exception as e:
            self.log("shutdown-fail %s" % e)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.wait(2000)
