import asyncio
import aiosqlite
import sqlite3
import time
import weakref
from datetime import datetime

from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QCoreApplication

from galacteek import log
from galacteek import ensure
from galacteek.ipfs import ipfsOp
from galacteek.dweb.atom import IPFSAtomFeedParser
from galacteek.dweb.atom import IPFSAtomFeedEntry
from galacteek.dweb.atom import IPFSAtomFeed
from galacteek.dweb.atom import AtomFeedExistsError
from galacteek.dweb.atom import AtomParseFeedError
from galacteek.ipfs.cidhelpers import IPFSPath


schemaScript = '''
CREATE TABLE if not exists atom_feeds
(id integer primary key, url text, scheme text, feed_id text,
category varchar(1, 128), autopin_entries integer, ctime timestamp);

CREATE TABLE if not exists atom_feed_history
(id integer primary key, atom_feed_id integer,
objpath text, status integer);

CREATE TABLE if not exists atom_feed_entries
(id integer primary key, atom_feed_id integer, entry_id text,
status integer, published timestamp);
'''


class SqliteDatabase:
    def __init__(self, dbPath):
        self._path = dbPath
        self._db = None
        self.feeds = AtomFeedsDatabase(self)

    @property
    def db(self):
        return self._db

    async def setup(self):
        try:
            self._db = await aiosqlite.connect(self._path)
            self._db.row_factory = aiosqlite.Row
        except:
            return False

        def adapt_datetime(ts):
            return time.mktime(ts.timetuple())

        sqlite3.register_adapter(datetime, adapt_datetime)

        try:
            await self.db.executescript(schemaScript)
        except Exception:
            log.debug('Error while executing schema script')
            return False

    async def close(self):
        await self.db.close()


class AtomFeedsDatabase(QObject):
    processedFeedEntry = pyqtSignal(IPFSAtomFeed, IPFSAtomFeedEntry)
    feedRemoved = pyqtSignal(str)

    def __init__(self, database, parent=None):
        super(AtomFeedsDatabase, self).__init__(parent)

        self.app = QCoreApplication.instance()
        self.loop = asyncio.get_event_loop()
        self.parser = IPFSAtomFeedParser()
        self.sqliteDb = database
        self.lock = asyncio.Lock()

        self._processTasksById = {}
        self._handled_by_id = weakref.WeakValueDictionary()

    @property
    def db(self):
        return self.sqliteDb.db

    def feedFromId(self, feedId):
        return self._handled_by_id.get(feedId)

    async def unfollow(self, feedId):
        with await self.lock:
            feed = await self.getFromId(feedId)

            if feed:
                task = self._processTasksById.get(feed['feed_id'])

                if task:
                    try:
                        await task.close()
                        del self._processTasksById[feed['feed_id']]
                    except Exception:
                        pass

                if feedId in self._handled_by_id:
                    del self._handled_by_id[feedId]

                params = {'id': feed['id']}
                query = '''
                    DELETE FROM atom_feed_entries
                    WHERE atom_feed_id=:id
                '''
                await self.db.execute(query, params)

                query = '''
                    DELETE FROM atom_feed_history
                    WHERE atom_feed_id=:id
                '''
                await self.db.execute(query, params)

                query = '''
                    DELETE FROM atom_feeds
                    WHERE id=:id
                '''
                await self.db.execute(query, params)
                await self.db.commit()

                self.feedRemoved.emit(feedId)
                return True

    @ipfsOp
    async def resolveAtomPath(self, ipfsop, path):
        iPath = IPFSPath(path, autoCidConv=True)
        if not iPath.valid:
            return None

        if iPath.isIpns:
            result = await ipfsop.nameResolveStreamFirst(path, timeout=10)
            if result:
                return result['Path']
        else:
            return iPath.objPath

    @ipfsOp
    async def follow(self, ipfsop, url):
        if not isinstance(url, str):
            raise ValueError('Wrong URL')

        path = IPFSPath(url)
        if not path.valid:
            raise ValueError('Wrong URL')

        scheme = path.scheme if path.scheme else 'dweb'

        resolved = await self.resolveAtomPath(str(path))
        if not resolved:
            raise ValueError('Does not resolve')

        try:
            feed = await self.parser.parse(resolved)
        except AtomParseFeedError:
            return False

        # Pin the resolved object (yeah!)
        await ipfsop.ctx.pin(resolved, qname='atom')

        #
        # Here's why Atom's a great choice over RSS for the dweb
        # Atom feeds *must* have an identifier
        # Using an IPNS path as the Atom feed identifier = uniqueness
        #

        # Same ID
        if await self.getFromId(feed.id):
            raise AtomFeedExistsError()

        # Same ID and URL (not necessarily the same)
        if await self.getFromUrlAndId(url, feed.id):
            raise AtomFeedExistsError()

        await self.db.execute(
            """INSERT INTO atom_feeds
            (url, scheme, feed_id, autopin_entries, ctime)
            VALUES (?, ?, ?, ?, ?)""",
            (url, scheme, feed.id, 1, datetime.now()))

        await self.db.commit()
        sqlObj = await self.getFromUrlAndId(url, feed.id)

        await self.db.execute(
            """INSERT INTO atom_feed_history
            (atom_feed_id, objpath, status)
            VALUES (?, ?, ?)""",
            (sqlObj['id'], resolved, 0))

        async with self.lock:
            await self.startFeedProcessTask(sqlObj)

        return True

    async def getFromId(self, feedId):
        query = '''
        SELECT *
        FROM atom_feeds
        WHERE feed_id=:feedid
        LIMIT 1
        '''
        cursor = await self.db.execute(query, {'feedid': feedId})
        return await cursor.fetchone()

    async def getFromUrlAndId(self, url, feedId):
        query = '''
        SELECT *
        FROM atom_feeds
        WHERE feed_id=:feedid AND url=:url
        LIMIT 1
        '''
        cursor = await self.db.execute(query,
                                       {'feedid': feedId, 'url': url})
        return await cursor.fetchone()

    async def allFeeds(self):
        query = 'SELECT * FROM atom_feeds'
        return await self.rows(query)

    async def processFeedTask(self, feedSql):
        while True:
            try:
                await self.processFeed(feedSql)
            except Exception:
                pass

            await asyncio.sleep(60)

    @ipfsOp
    async def processFeed(self, ipfsop, feedSql):
        while True:
            path = IPFSPath(feedSql['url'])

            log.debug('Atom Feed (URL: {url}): Resolving {objpath}'.format(
                url=feedSql['url'], objpath=path.objPath))

            resolved = await self.resolveAtomPath(path.objPath)

            if not resolved:
                # TODO
                log.debug('Atom Feed (URL {url}): resolve failed'.format(
                    url=feedSql['url']))
                await ipfsop.sleep(60)
                continue
            else:
                log.debug('Atom Feed (URL: {url}): Resolved to {r}'.format(
                    url=feedSql['url'], r=resolved))
                await ipfsop.ctx.pin(resolved, qname='atom')

            await ipfsop.sleep()

            needParse = True
            historyObj = await self.feedObjectHistory(
                feedSql['id'], resolved)

            if not historyObj:
                historyObjId = await self.feedNewObjectHistory(
                    feedSql['id'], resolved)
            else:
                historyObjId = historyObj['id']
                needParse = False

            atomFeed = self.feedFromId(feedSql['feed_id'])

            if not atomFeed or needParse:
                atomFeed = await self.atomParseObject(resolved)
                if not atomFeed:
                    log.debug(f'processFeed: failed to parse {resolved}')
                    await ipfsop.sleep(60)
                    continue

            await self.loadFeedEntries(feedSql, atomFeed)

            # Mark the object as processed
            await self.feedObjectHistoryUpdateStatus(historyObjId,
                                                     resolved, 1)

            log.debug(f'processFeed {path}: success')
            await ipfsop.sleep(180)

    async def atomParseObject(self, path):
        try:
            atomFeed = await self.parser.parse(path)
        except AtomParseFeedError:
            log.debug('Atom: failed to parse {p}'.format(
                p=path))
        else:
            return atomFeed

    @ipfsOp
    async def loadFeedEntries(self, ipfsop, feedSql, atomFeed):
        entries = await self.searchEntries(atomFeed.id)
        existingIds = [ent['entry_id'] for ent in entries]

        self._handled_by_id[atomFeed.id] = atomFeed

        for entry in atomFeed.entries:
            await asyncio.sleep(0.1)

            if not isinstance(entry.id, str):
                continue

            if entry.id not in existingIds:
                _rid = await self.addEntry(feedSql['id'], entry.id)

                entry.status = IPFSAtomFeedEntry.ENTRY_STATUS_NEW
                entry.srow_id = _rid
                self.processedFeedEntry.emit(atomFeed, entry)

                if feedSql['autopin_entries'] == 1 and \
                        feedSql['scheme'] in ['ipns', 'ipfs', 'dweb'] and 0:
                    # Disable autopin for now
                    path = IPFSPath(entry.id)
                    if path.valid:
                        log.debug('Atom: autopinning {id}'.format(
                            id=entry.id))
                        ensure(ipfsop.pin(
                            path.objPath, recursive=False, timeout=10)
                        )
                        await ipfsop.sleep(0.5)
            else:
                for exent in entries:
                    if exent['entry_id'] == entry.id:
                        entry.status = exent['status']
                        entry.srow_id = exent['id']
                        self.processedFeedEntry.emit(atomFeed,
                                                     entry)

    async def searchEntries(self, feedId):
        query = '''
        SELECT atom_feed_entries.id,
               atom_feed_entries.entry_id,
               atom_feed_entries.status
        FROM atom_feed_entries
        INNER JOIN atom_feeds ON
            atom_feeds.id = atom_feed_entries.atom_feed_id
        WHERE atom_feeds.feed_id=:feedid
        '''

        return await self.rows(query, {'feedid': feedId})

    async def feedHasObjectInHistory(self, feedId, objPath, status=0):
        query = '''
        SELECT DISTINCT atom_feed_history.objpath
        FROM atom_feed_history
        INNER JOIN atom_feeds ON
            atom_feeds.id = atom_feed_history.atom_feed_id
        WHERE atom_feeds.feed_id=:feedid AND status=:status AND
            atom_feed_history.objpath=:objpath
        '''

        params = {'feedid': feedId, 'status': status, 'objpath': objPath}
        cursor = await self.db.execute(query, params)
        return await cursor.fetchone()

    async def feedObjectHistory(self, feedId, objPath):
        query = '''
        SELECT *
        FROM atom_feed_history
        INNER JOIN atom_feeds ON
            atom_feeds.id = atom_feed_history.atom_feed_id
        WHERE atom_feeds.id=:feedid AND
            atom_feed_history.objpath=:objpath
        '''

        params = {'feedid': feedId, 'objpath': objPath}
        cursor = await self.db.execute(query, params)
        return await cursor.fetchone()

    async def feedObjectHistoryLast(self, feedId):
        query = '''
        SELECT objpath
        FROM atom_feed_history
        INNER JOIN atom_feeds ON
            atom_feeds.id = atom_feed_history.atom_feed_id
        WHERE atom_feeds.id=:feedid
        ORDER BY atom_feed_history.id DESC
        LIMIT 1
        '''

        params = {'feedid': feedId}
        cursor = await self.db.execute(query, params)
        return await cursor.fetchone()

    async def feedObjectHistoryUpdateStatus(self, historyId, objPath, status):
        query = '''
        UPDATE atom_feed_history
        SET status=:status
        WHERE id=:historyid AND objpath=:objpath
        '''

        params = {'historyid': historyId, 'objpath': objPath, 'status': status}
        await self.db.execute(query, params)
        await self.db.commit()

    async def feedNewObjectHistory(self, feedId, objPath):
        cursor = await self.db.execute(
            """INSERT INTO atom_feed_history
            (atom_feed_id, objpath, status)
            VALUES (?, ?, ?)""",
            (feedId, objPath, 0))
        await self.db.commit()
        return cursor.lastrowid

    async def rows(self, query, params={}):
        rows = []
        async with self.db.execute(query, params) as cursor:
            async for row in cursor:
                await asyncio.sleep(0)
                rows.append(row)
        return rows

    async def addEntry(self, feedId, entryId,
                       status=IPFSAtomFeedEntry.ENTRY_STATUS_NEW):
        cursor = await self.db.execute(
            """INSERT INTO atom_feed_entries
            (atom_feed_id, entry_id, status, published)
            VALUES (?, ?, ?, ?)""",
            (feedId, entryId, status, datetime.now()))
        await self.db.commit()
        return cursor.lastrowid

    async def feedEntrySetStatus(self, entryId, status):
        query = '''
        UPDATE atom_feed_entries
        SET status=:status
        WHERE id=:id
        '''

        params = {'id': entryId, 'status': status}
        await self.db.execute(query, params)
        await self.db.commit()

    async def start(self):
        await self.app.scheduler.spawn(self.processTask())

    async def preload(self):
        feeds = await self.allFeeds()

        try:
            for feed in feeds:
                last = await self.feedObjectHistoryLast(feed['id'])

                if last:
                    atomFeed = await self.atomParseObject(last['objpath'])
                    if not atomFeed:
                        continue

                    await self.loadFeedEntries(feed, atomFeed)
        except Exception as err:
            log.debug('Exception preloading feeds: {e}'.format(
                e=str(err)))

    async def startFeedProcessTask(self, feed):
        # Start process task for feed if not already started

        pTask = self._processTasksById.get(feed['feed_id'])
        if not pTask:
            self._processTasksById[feed['feed_id']] = \
                await self.app.scheduler.spawn(self.processFeed(feed))

    async def processTask(self):
        await self.preload()

        try:
            while True:
                feeds = await self.allFeeds()

                async with self.lock:
                    for feed in feeds:
                        await self.startFeedProcessTask(feed)

                await asyncio.sleep(30)
        except asyncio.CancelledError:
            log.debug('processTask: cancelled')
            return
        except Exception:
            return
