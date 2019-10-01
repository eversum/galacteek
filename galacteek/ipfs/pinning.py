import asyncio
import json
import os.path
import time

import aioipfs

from galacteek import log
from galacteek import ensure
from galacteek.ipfs.wrappers import ipfsOp


class Cancelled(Exception):
    pass


class PinningMaster(object):
    """ Pins objects on request through an async queue """

    def __init__(self, ctx, checkPinned=False, statusFilePath=None):
        self.lock = asyncio.Lock()
        self._ordersQueue = asyncio.Queue()
        self._ctx = ctx
        self._pinStatus = {}
        self._processTask = None
        self._statusFilePath = statusFilePath
        self._checkPinned = checkPinned
        self._sCleanupLast = None
        self._maxStalledMessages = 48

        ctx.app.marksLocal.markAdded.connect(self.onMarkAdded)

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

    def onMarkAdded(self, mPath, mData):
        if 'pin' in mData and isinstance(mData['pin'], dict):
            if mData['pin']['single'] is True:
                ensure(self.queue(mPath, False, None, qname='hashmarks'))
            elif mData['pin']['recursive'] is True:
                ensure(self.queue(mPath, True, None, qname='hashmarks'))

    def debug(self, msg, **kwargs):
        log.debug('Pinning service: {}'.format(msg), **kwargs)

    def queueStatus(self, qname):
        return self.pinStatus.get(qname, None)

    def status(self, all=False):
        export = {}

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

    def activeItemsCount(self):
        count = 0
        for qname, items in self.status().items():
            count += len(items)
        return count

    async def cleanupStatus(self, pinnedExpires=60 * 2):
        now = int(time.time())

        if isinstance(self._sCleanupLast, int):
            if now - self._sCleanupLast < 60:
                return

        toDelete = []
        try:
            with await self.lock:
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

    def _emitItemsCount(self):
        self.ipfsCtx.pinItemsCount.emit(self.activeItemsCount())

    def pathRegister(self, qname, path, recursive):
        if qname not in self.pinStatus:
            self._pinStatus[qname] = {}

        self._pinStatus[qname][path] = {
            'recursive': recursive,
            'status': None,
            'ts_queued': int(time.time()),
            'ts_pinned': 0,
            'pinned': False,
            'cancel': False
        }

        self.ipfsCtx.pinNewItem.emit(path)
        self._emitItemsCount()
        return self.pinStatus[qname][path]

    def statusFromPath(self, path, qname='default'):
        if qname in self.pinStatus:
            return self.pinStatus[qname].get(path, None)

    async def pathDelete(self, path):
        with await self.lock:
            for qname, queue in self.pinStatus.items():
                if path in queue:
                    self.debug('Deleting item {item}'.format(
                        item=self.pinStatus[qname][path]))
                    del self._pinStatus[qname][path]
                    self.ipfsCtx.pinItemRemoved.emit(qname, path)
        self._emitItemsCount()

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

        pItem = self.pathRegister(qname, path, recursive)

        try:
            stalledCn = 0
            lastPTime = None

            async for pinned in op.client.pin.add(path, recursive=recursive):
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
                else:
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
                self._emitItemsCount()

            return (path, 0, 'OK')

    async def queue(self, path, recursive, onSuccess, qname='default'):
        """ Queue an item for processing """
        await self.ordersQueue.put((qname, path, recursive, onSuccess))
        self.ipfsCtx.pinQueueSizeChanged.emit(self.ordersQueue.qsize())

    async def start(self):
        self._processTask = self.ipfsCtx.loop.create_task(self.process())

    async def stop(self):
        if self._processTask:
            self._processTask.cancel()
            await self._processTask
        self.saveStatus()

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

    def saveStatus(self):
        with open(self._statusFilePath, 'w+t') as fd:
            fd.write(json.dumps(self.status(), indent=4))

    def cancel(self, qname, path):
        status = self.statusFromPath(path, qname=qname)
        if status:
            status['cancel'] = True

    async def process(self):
        if os.path.exists(self._statusFilePath):
            try:
                data = None
                with open(self._statusFilePath, 'rt') as fd:
                    data = json.load(fd)
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
                    f = asyncio.ensure_future(
                        self.pin(path, recursive=recursive, qname=qname))
                    if callback:
                        f.add_done_callback(callback)
                except Exception:
                    self.debug('Invalid item in queue')
                    continue
        except asyncio.CancelledError:
            self.debug('Task was cancelled')
