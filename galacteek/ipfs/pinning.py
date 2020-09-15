import asyncio
import aiofiles
import orjson
import os.path
import time

import aioipfs

from galacteek import log
from galacteek import ensure
from galacteek import database
from galacteek.ipfs.wrappers import ipfsOp


class Cancelled(Exception):
    pass


class PinningMaster(object):
    """ Pins objects on request through an async queue """

    def __init__(self, ctx, checkPinned=False, statusFilePath=None):
        self.lock = asyncio.Lock()
        self.sflock = asyncio.Lock()
        self._ordersQueue = asyncio.Queue()
        self._ctx = ctx
        self._pinStatus = {}
        self._processTask = None
        self._statusFilePath = statusFilePath
        self._checkPinned = checkPinned
        self._sCleanupLast = None
        self._maxStalledMessages = 24

        database.HashmarkAdded.connectTo(self.onMarkAdded)

    @property
    def ordersQueue(self):
        return self._ordersQueue

    @property
    def ipfsCtx(self):
        return self._ctx

    @property
    def pinStatus(self):
        return self._pinStatus

    @property
    def queuesNames(self):
        return list(self.pinStatus.keys())

    async def onMarkAdded(self, hashmark):
        if hashmark.pin == hashmark.PIN_SINGLE:
            ensure(self.queue(hashmark.path, False, None, qname='hashmarks'))
        elif hashmark.pin == hashmark.PIN_RECURSIVE:
            ensure(self.queue(hashmark.path, True, None, qname='hashmarks'))

    def debug(self, msg, **kwargs):
        log.debug('Pinning service: {}'.format(msg), **kwargs)

    def queueStatus(self, qname):
        return self.pinStatus.get(qname, None)

    async def status(self, all=False):
        export = {}

        async with self.lock:
            for qname, queue in self.pinStatus.items():
                for path, pinData in queue.items():
                    if pinData['pinned'] is True and all is False:
                        continue
                    exportQ = export.setdefault(qname, [])
                    progress = None
                    if pinData['status']:
                        progress = pinData['status'].get('Progress', 'Unknown')
                    exportQ.append({
                        'path': path,
                        'recursive': pinData['recursive'],
                        'pinned': pinData['pinned'],
                        'ts_queued': pinData['ts_queued'],
                        'progress': progress
                    })

        return export

    async def activeItemsCount(self):
        count = 0
        try:
            status = await self.status()

            for qname, items in status.items():
                count += len(items)
        except Exception:
            pass

        return count

    async def cleanupStatus(self, pinnedExpires=60 * 2):
        now = int(time.time())

        if isinstance(self._sCleanupLast, int):
            if now - self._sCleanupLast < 60:
                return

        toDelete = []
        try:
            async with self.lock:
                for qname, queue in self.pinStatus.items():
                    for path, pinData in queue.items():
                        if pinData['pinned'] is False:
                            continue

                        if pinData['ts_pinned'] > 0 and \
                                now - pinData['ts_pinned'] > pinnedExpires:
                            toDelete.append(path)
        except BaseException:
            self.debug('Cleanup status error')
        else:
            self._sCleanupLast = now
            for path in toDelete:
                await self.pathDelete(path)

    async def _emitItemsCount(self):
        self.ipfsCtx.pinItemsCount.emit(await self.activeItemsCount())

    async def pathRegistered(self, path):
        async with self.lock:
            for qname, queue in self.pinStatus.items():
                if path in queue:
                    return True

        return False

    async def pathRegister(self, qname, path, recursive):
        async with self.lock:
            cont = self._pinStatus.setdefault(qname, {})
            cont[path] = {
                'recursive': recursive,
                'status': None,
                'ts_queued': int(time.time()),
                'ts_pinned': 0,
                'pinned': False,
                'cancel': False
            }

        self.ipfsCtx.pinNewItem.emit(path)
        await self._emitItemsCount()
        return self.pinStatus[qname][path]

    async def statusFromPath(self, path, qname='default'):
        async with self.lock:
            if qname in self.pinStatus:
                return self.pinStatus[qname].get(path, None)

    async def pathDelete(self, path):
        async with self.lock:
            for qname, queue in self.pinStatus.items():
                if path in queue:
                    self.debug('Deleting item {item}'.format(
                        item=self.pinStatus[qname][path]))
                    del self._pinStatus[qname][path]
                    self.ipfsCtx.pinItemRemoved.emit(qname, path)

        await self._emitItemsCount()

    @ipfsOp
    async def pin(self, op, path, recursive=False, qname='default'):
        """
        Pin the object referenced by ``path``

        Returns a (path, statuscode, errmsg) tuple
        """
        self.debug('Pinning object {path} to {qname} (recursive {rec})'.format(
            path=path, rec=recursive, qname=qname))

        if self._checkPinned:
            if await op.isPinned(path):
                # Already pinned
                self.debug('Already pinned: {path}'.format(path=path))
                await self.pathDelete(path)
                return (path, 0, 'Already pinned')

        pItem = await self.pathRegister(qname, path, recursive)

        await self.saveStatus()

        try:
            stalledCn = 0
            lastPTime = None

            async for pinned in op.client.pin.add(
                    await op.objectPathMapper(path), recursive=recursive):
                await asyncio.sleep(0)

                now = time.time()

                if pItem['cancel'] is True:
                    raise Cancelled()

                pins = pinned.get('Pins', None)
                progress = pinned.get('Progress', None)

                if progress:
                    lastPTime = now
                    self.debug('Progress {0}: {1}'.format(path, progress))

                if pinned != pItem['status']:
                    pItem['status'] = pinned
                    self.ipfsCtx.pinItemStatusChanged.emit(qname, path, pItem)

                if pins is None and progress is None and not lastPTime:
                    # Never received any progress status yet
                    stalledCn += 1

                if stalledCn >= self._maxStalledMessages:
                    self.debug('{0}: stalled (removing)'.format(path))
                    await self.pathDelete(path)
                    return (path, 2, 'Stalled')

                await asyncio.sleep(1)
        except aioipfs.APIError as err:
            self.debug('Pinning error {path}: {msg}'.format(
                path=path, msg=err.message))
            await self.pathDelete(path)
            return (path, 1, err.message)
        except asyncio.CancelledError:
            self.debug('Pinning was cancelled for {path}'.format(path=path))
            await self.pathDelete(path)
            return (path, 2, 'Cancelled')
        except Cancelled:
            await self.pathDelete(path)
            return (path, 2, 'Cancelled')
        else:
            self.debug('Queue {qname}: pinning success for {path}'.format(
                qname=qname, path=path))

            pins = pItem['status'].get('Pins', None)
            if pins and isinstance(pins, list):
                # 'Pins' is a list of CIDs, mark it as pinned
                now = int(time.time())
                pItem['pinned'] = True
                pItem['ts_pinned'] = now
                self.ipfsCtx.pinFinished.emit(path)

            await self.saveStatus()

            await self._emitItemsCount()

            return (path, 0, 'OK')

    async def queue(self, path, recursive, onSuccess, qname='default'):
        """ Queue an item for processing """
        await self.ordersQueue.put((qname, path, recursive, onSuccess))
        self.ipfsCtx.pinQueueSizeChanged.emit(self.ordersQueue.qsize())

    async def start(self):
        self._processTask = await self.ipfsCtx.app.scheduler.spawn(
            self.process())

    async def stop(self):
        if self._processTask:
            await self._processTask.close()

        await self.saveStatus()

    def restoreStatus(self, data):
        if not isinstance(data, dict):
            return

        for qname, items in data.items():
            for item in items:
                path = item.get('path', None)
                recursive = item.get('recursive', False)

                if path:
                    self.debug('Restoring item: {path} {recursive}'.format(
                        path=path, recursive=recursive))
                    ensure(self.queue(path, recursive, None, qname=qname))

    async def saveStatus(self):
        async with self.sflock:
            async with aiofiles.open(self._statusFilePath, 'w+b') as fd:
                await fd.write(orjson.dumps(await self.status()))

    async def cancel(self, qname, path):
        status = await self.statusFromPath(path, qname=qname)
        if status:
            status['cancel'] = True
            await self.saveStatus()

    async def process(self):
        if os.path.exists(self._statusFilePath):
            try:
                data = None
                with open(self._statusFilePath, 'rt') as fd:
                    data = orjson.loads(fd.read())
            except Exception:
                self.debug('Could not load pin status file')
            else:
                if isinstance(data, dict):
                    self.restoreStatus(data)

        try:
            while True:
                await self.cleanupStatus()

                item = await self.ordersQueue.get()
                if item is None:
                    self.debug('null item in queue')
                    continue

                self.ipfsCtx.pinQueueSizeChanged.emit(self.ordersQueue.qsize())

                try:
                    qname, path, recursive, callback = item

                    if await self.pathRegistered(path):
                        self.debug(f'{path}: already queued')
                        continue

                    f = asyncio.ensure_future(
                        self.pin(path, recursive=recursive, qname=qname))
                    if callback:
                        f.add_done_callback(callback)
                except Exception:
                    self.debug('Invalid item in queue')
                    continue
        except asyncio.CancelledError:
            self.debug('Task was cancelled')
