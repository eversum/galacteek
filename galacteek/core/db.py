import asyncio
import aiosqlite
import sqlite3
import time
import weakref
from datetime import datetime

from PyQt5.QtCore import QUrl
from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal

from galacteek import log
from galacteek import ensure
from galacteek.ipfs import ipfsOp
from galacteek.core.schemes import SCHEME_DWEB
from galacteek.core.schemes import SCHEME_IPFS
from galacteek.dweb.atom import IPFSAtomFeedParser
from galacteek.dweb.atom import IPFSAtomFeedEntry
from galacteek.dweb.atom import IPFSAtomFeed
from galacteek.dweb.atom import AtomFeedExistsError
from galacteek.dweb.atom import AtomParseFeedError
from galacteek.ipfs.cidhelpers import IPFSPath


schemaScript = '''
CREATE TABLE if not exists url_history_items
(id integer primary key, url text, scheme text,
rootcid text, rootcidv integer, ctime timestamp);

CREATE TABLE if not exists url_history_visits
(history_item_id integer, title text, atime timestamp);

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

    async def historySearch(self, input):
        rows = []
        query = '''
        SELECT DISTINCT url, title, scheme, rootcid, rootcidv, id
        FROM url_history_visits
        INNER JOIN url_history_items ON
            url_history_items.id = url_history_visits.history_item_id
        WHERE url LIKE '%{input}%' OR title LIKE '%{input}%'
        COLLATE NOCASE
        ORDER BY atime desc'''

        _urls = []
        async with self.db.execute(query.format(input=input)) as cursor:
            async for row in cursor:
                if row['url'] in _urls:
                    continue

                _urls.append(row['url'])

                await asyncio.sleep(0)
                rows.append(row)
        return rows

    async def historyRecord(self, url, title):
        urlItemId = None
        existing = await self.historySearch(url)

        if len(existing) > 0:
            urlItemId = existing.pop()['id']
        else:
            qUrl = QUrl(url)
            scheme = qUrl.scheme() if qUrl.isValid() else ''

            rootcid = ''
            rootcidv = None

            if scheme in [SCHEME_DWEB, SCHEME_IPFS]:
                ipfsPath = IPFSPath(url)
                if ipfsPath.valid and ipfsPath.rootCid:
                    rootcid = str(ipfsPath.rootCid)
                    rootcidv = ipfsPath.rootCid.version

            cursor = await self.db.execute(
                """INSERT INTO url_history_items
                (url, scheme, rootcid, rootcidv, ctime)
                VALUES (?, ?, ?, ?, ?)""",
                (url, scheme, rootcid, rootcidv, datetime.now()))
            urlItemId = cursor.lastrowid

        cursor = await self.db.execute(
            """INSERT INTO url_history_visits
            (history_item_id, title, atime) VALUES (?, ?, ?)""",
            (urlItemId, title, datetime.now()))

        await self.db.commit()
        return True

    async def historyClear(self, before=None):
        if before:
            cursor = await self.db.execute(
                "DELETE FROM url_history_items WHERE ctime < {0}".format(
                    before))
            log.debug('Cleared {} history records'.format(cursor.rowcount))

            await self.db.execute(
                "DELETE FROM url_history_visits WHERE atime < {0}".format(
                    before))
        else:
            # Clear all
            cursor = await self.db.execute(
                'DELETE FROM url_history_items'
            )
            log.debug('Cleared {} history records'.format(cursor.rowcount))
            await self.db.execute(
                'DELETE FROM url_history_visits'
            )

        await self.db.commit()

    async def close(self):
        await self.db.close()


class AtomFeedsDatabase(QObject):
    processedFeedEntry = pyqtSignal(IPFSAtomFeed, IPFSAtomFeedEntry)
    feedRemoved = pyqtSignal(str)

    def __init__(self, database, parent=None):
        super(AtomFeedsDatabase, self).__init__(parent)

        self.loop = asyncio.get_event_loop()
        self.parser = IPFSAtomFeedParser()
        self.sqliteDb = database
        self.lock = asyncio.Lock()

        self._handled_by_id = weakref.WeakValueDictionary()
        self._process_task = None

    @property
    def db(self):
        return self.sqliteDb.db

    def feedFromId(self, feedId):
        return self._handled_by_id.get(feedId)

    async def unfollow(self, feedId):
        with await self.lock:
            feed = await self.getFromId(feedId)

            if feed:
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
    async def follow(self, ipfsop, url):
        if not isinstance(url, str):
            raise ValueError('Wrong URL')

        path = IPFSPath(url)
        if not path.valid:
            raise ValueError('Wrong URL')

        scheme = 'dweb'

        try:
            feed = await self.parser.parse(path)
        except AtomParseFeedError:
            return False

        resolved = await ipfsop.resolve(str(path))
        if not resolved:
            raise ValueError('Does not resolve')

        # Pin the resolved object (yeah!)
        await ipfsop.pin(resolved)

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

        await self.processFeed(sqlObj)
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

    @ipfsOp
    async def processFeed(self, ipfsop, feedSql):
        with await self.lock:
            path = IPFSPath(feedSql['url'])
            resolved = await ipfsop.resolve(path.objPath)
            if not resolved:
                # TODO
                return

            await ipfsop.sleep()

            historyObj = await self.feedObjectHistory(
                feedSql['id'], resolved)

            if not historyObj:
                historyObjId = await self.feedNewObjectHistory(
                    feedSql['id'], resolved)
            else:
                historyObjId = historyObj['id']

            atomFeed = self.feedFromId(feedSql['feed_id'])

            if not atomFeed:
                try:
                    atomFeed = await self.parser.parse(resolved)
                except AtomParseFeedError:
                    return False

            self._handled_by_id[atomFeed.id] = atomFeed

            entries = await self.searchEntries(atomFeed.id)
            existingIds = [ent['entry_id'] for ent in entries]

            for entry in atomFeed.entries:
                await asyncio.sleep(0.2)
                if not isinstance(entry.id, str):
                    continue

                if entry.id not in existingIds:
                    _rid = await self.addEntry(feedSql['id'], entry.id)

                    entry.status = IPFSAtomFeedEntry.ENTRY_STATUS_NEW
                    entry.srow_id = _rid
                    self.processedFeedEntry.emit(atomFeed, entry)

                    if feedSql['autopin_entries'] == 1 and \
                            feedSql['scheme'] == 'dweb':
                        path = IPFSPath(entry.id)
                        if path.valid:
                            log.debug('Atom: autopinning {id}'.format(
                                id=entry.id))
                            ensure(ipfsop.pin(path.objPath))
                else:
                    for exent in entries:
                        if exent['entry_id'] == entry.id:
                            entry.status = exent['status']
                            entry.srow_id = exent['id']
                            self.processedFeedEntry.emit(atomFeed,
                                                         entry)

            # Mark the object as processed
            await self.feedObjectHistoryUpdateStatus(historyObjId,
                                                     resolved, 1)

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
        if not self._process_task:
            self._process_task = self.loop.create_task(self.processTask())

    async def processTask(self):
        while True:
            feeds = await self.allFeeds()

            for feed in feeds:
                await self.processFeed(feed)

            await asyncio.sleep(300)
