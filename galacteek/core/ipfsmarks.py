import json
import time
import sys
import collections
import copy
import re
import os.path
import asyncio
from datetime import datetime

import aiofiles

from galacteek import log
from galacteek.ipfs.cidhelpers import IPFSPath

from PyQt5.QtCore import pyqtSignal, QObject


class MarksEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, IPFSHashMark):
            return obj.data
        return json.JSONEncoder.default(self, obj)


marksKey = '_marks'
pyramidsKey = '_pyramids'
pyramidsMarksKey = '_pyramidmarks'


def rSlash(path):
    return path.rstrip('/')


def categoryValid(category):
    return re.match('^([0-9A-Za-z-_/]+)$', category) is not None


class IPFSHashMark(collections.UserDict):
    @property
    def markData(self):
        return self.data[self.path]

    @property
    def dtcreated(self):
        dtime = self.markData['datecreated']
        try:
            return datetime.strptime(dtime, '%Y-%m-%dT%H:%M:%S.%f')
        except:
            return datetime.strptime(dtime, '%Y-%m-%d %H:%M:%S')

    def addTags(self, tags):
        self.data[self.path]['tags'] += tags

    def dump(self):
        print(json.dumps(self.data, indent=4))

    @staticmethod
    def fromJson(mPath, metadata):
        if not IPFSPath(mPath).valid or not isinstance(metadata, dict):
            return None

        hmark = IPFSHashMark({mPath: metadata})
        hmark.path = mPath
        return hmark

    @staticmethod
    def make(path, title=None, datecreated=None, share=False, tags=[],
             description='', comment='', datasize=None, cumulativesize=None,
             numlinks=None, icon=None, pinSingle=False, pinRecursive=False):
        if datecreated is None:
            datecreated = datetime.now().isoformat()

        path = rSlash(path)

        mData = IPFSHashMark({
            path: {
                'metadata': {
                    'title': title,
                    'description': description,
                    'datasize': datasize,
                    'cumulativesize': cumulativesize,
                    'numlinks': numlinks,
                },
                'pin': {
                    'single': pinSingle,
                    'recursive': pinRecursive,
                    'filters': []
                },
                'datecreated': datecreated,
                'tscreated': int(time.time()),
                'comment': comment,
                'icon': icon,
                'share': share,
                'tags': tags,
            }
        })

        mData.path = path
        return mData


class MultihashPyramid(collections.UserDict):
    # Types
    TYPE_STANDARD = 0

    # Flags
    FLAG_MODIFIABLE_BYUSER = 0x01

    @property
    def p(self):
        return self.data[self.name]

    @property
    def marks(self):
        return self.p[pyramidsMarksKey]

    @property
    def marksCount(self):
        return len(self.marks)

    @property
    def empty(self):
        return self.marksCount == 0

    @property
    def latest(self):
        return self.p['latest']

    @latest.setter
    def latest(self, value):
        self.p['latest'] = value

    @property
    def icon(self):
        return self.p['icon']

    @property
    def description(self):
        return self.p['description']

    @property
    def ipnsKey(self):
        return self.p['ipns']['publishtokey']

    @property
    def ipnsAllowOffline(self):
        return self.p['ipns']['allowoffline']

    @property
    def ipnsLifetime(self):
        return self.p['ipns']['lifetime']

    @staticmethod
    def make(name, description='Pyramid', icon=None, ipnskey=None,
             internal=False, publishdelay=0, comment=None, flags=0,
             allowoffline=True, lifetime='48h'):
        datecreated = datetime.now().isoformat()
        pyramid = MultihashPyramid({
            name: {
                'ipns': {
                    'publishtokey': ipnskey,
                    'publishdelay': publishdelay,
                    'allowoffline': allowoffline,
                    'ttl': None,
                    'lifetime': lifetime
                },
                'datecreated': datecreated,
                'icon': icon,
                'latest': None,
                'description': description,
                'comment': comment,
                'type': MultihashPyramid.TYPE_STANDARD,
                'internal': internal,
                'flags': flags,
                pyramidsMarksKey: []  # list of hashmarks in the pyramid
            }
        })

        pyramid.name = name
        return pyramid


class IPFSMarks(QObject):
    changed = pyqtSignal()
    markDeleted = pyqtSignal(str)
    markAdded = pyqtSignal(str, dict)
    feedMarkAdded = pyqtSignal(str, IPFSHashMark)

    pyramidConfigured = pyqtSignal(str)
    pyramidAddedMark = pyqtSignal(str, IPFSHashMark)
    pyramidCapstoned = pyqtSignal(str)
    pyramidNeedsPublish = pyqtSignal(str, IPFSHashMark)
    pyramidChanged = pyqtSignal(str)
    pyramidEmpty = pyqtSignal(str)

    def __init__(self, path, parent=None, data=None, autosave=True):
        super().__init__(parent)

        self._path = path
        self._autosave = autosave
        self._marks = data if data else self.load()
        self.changed.connect(self.onChanged)
        self.lastsaved = time.time()
        self.changed.emit()

        self.pyramidCapstoned.connect(self.onPyramidCapstone)

    @property
    def path(self):
        return self._path

    @property
    def autosave(self):
        return self._autosave

    @property
    def root(self):
        return self._marks

    @property
    def _root(self):
        return self._marks

    @property
    def _rootMarks(self):
        return self._root['ipfsmarks']

    @property
    def _rootCategories(self):
        return self._rootMarks['categories']

    @property
    def _rootFeeds(self):
        return self._root['feeds']

    def skeleton(self):
        return {
            'ipfsmarks': {
                'categories': {}
            },
            'feeds': {}
        }

    def load(self):
        if not self.path:
            return self.skeleton()
        try:
            with open(self.path, 'rt') as fd:
                marks = json.load(fd)
            return marks
        except Exception:
            marks = collections.OrderedDict()

        if 'ipfsmarks' not in marks:
            marks = self.skeleton()

        return marks

    def onChanged(self):
        if self.autosave is True:
            self.save()

    def save(self):
        """ Save synchronously """
        if not self.path:  # don't save
            return
        try:
            with open(self.path, 'w+t') as fd:
                self.serialize(fd)
                self.lastsaved = time.time()
        except BaseException:
            log.debug('Could not save hashmarks ({0}'.format(
                self.path))

    async def saveAsync(self):
        async with aiofiles.open(self.path, 'w+t') as fd:
            await fd.write(json.dumps(self._root, indent=4, cls=MarksEncoder))
            self.lastsaved = time.time()

    def hasCategory(self, category, parent=None):
        if parent is None:
            parent = self._rootCategories
        return category in parent

    def enterCategory(self, section, create=False):
        comps = section.lstrip('/').rstrip('/').split('/')
        return self.walk(comps, create=create)

    def walk(self, path, create=True):
        """
        Walk to a category and create intermediary parents if create
        is True. path is a list of category components
        e.g ['general', 'news'] for category path /general/news
        """
        def _walk(path, parent=None):
            for p in path:
                if p.startswith('_'):
                    return
                if p in parent.keys():
                    parent = parent[p]
                elif p not in parent.keys() and create is True:
                    self.addCategory(p, parent=parent)
                    parent = parent[p]
                else:
                    return
            return parent
        return _walk(path, parent=self._rootCategories)

    def getCategories(self):
        def _list(path, parent=None):
            for p in parent.keys():
                if p.startswith('_'):
                    continue

                fullPath = path + [p]
                yield '/'.join(fullPath)
                yield from _list(fullPath, parent=parent[p])

        return list(_list([], parent=self._rootCategories))

    def addCategory(self, category, parent=None):
        if parent is None:
            parent = self._rootCategories

        if len(category) > 256:
            return None

        if not self.hasCategory(category, parent=parent):
            parent[category] = {
                marksKey: {},
                pyramidsKey: {}
            }
            self.changed.emit()
            return parent[category]

    def getCategoryMarks(self, category, usecopy=False):
        sec = self.enterCategory(category)
        if sec:
            if usecopy:
                return copy.copy(sec[marksKey])
            else:
                return sec[marksKey]

    def isInCategory(self, category, path):
        sec = self.enterCategory(category)
        if sec:
            return path in sec[marksKey]

    def getAll(self, share=False):
        cats = self.getCategories()
        _all = {}
        for cat in cats:
            catMarks = self.getCategoryMarks(cat)
            for mpath, mark in catMarks.items():
                if mark['share'] == share:
                    _all[mpath] = mark
        return _all

    def searchAllByMetadata(self, metadata):
        # todo: deprecate searchByMetadata
        if not isinstance(metadata, dict):
            raise ValueError('Metadata needs to be a dictionary')

        categories = self.getCategories()

        title = metadata.get('title', None)
        descr = metadata.get('description', None)
        path = metadata.get('path', None)

        def metaMatch(mark, field, regexp):
            try:
                if mark['metadata'][field] and re.search(
                        regexp, mark['metadata'][field],
                        re.IGNORECASE):
                    return True
            except:
                return False

        for cat in categories:
            marks = self.getCategoryMarks(cat)
            if not marks:
                continue

            for mPath, mark in marks.items():
                if 'metadata' not in mark:
                    continue

                if path and path == mPath:
                    yield IPFSHashMark.fromJson(mPath, mark)
                    continue

                if title and metaMatch(mark, 'title', title):
                    yield IPFSHashMark.fromJson(mPath, mark)
                    continue

                if descr and metaMatch(mark, 'description', descr):
                    yield IPFSHashMark.fromJson(mPath, mark)
                    continue

    def searchByMetadata(self, metadata):
        if not isinstance(metadata, dict):
            raise ValueError('Metadata needs to be a dictionary')

        categories = self.getCategories()

        title = metadata.get('title', None)
        descr = metadata.get('description', None)
        path = metadata.get('path', None)

        def metaMatch(mark, field, regexp):
            try:
                if mark['metadata'][field] and re.search(
                        regexp, mark['metadata'][field]):
                    return True
            except:
                return False

        for cat in categories:
            marks = self.getCategoryMarks(cat)
            if not marks:
                continue

            for mPath, mark in marks.items():
                if 'metadata' not in mark:
                    continue

                if path and path == mPath:
                    return IPFSHashMark.fromJson(mPath, mark)

                if title and metaMatch(mark, 'title', title):
                    return IPFSHashMark.fromJson(mPath, mark)

                if descr and metaMatch(mark, 'description', descr):
                    return IPFSHashMark.fromJson(mPath, mark)

        return None

    def find(self, bpath, category=None, delete=False):
        ipfsPath = IPFSPath(bpath)
        if not ipfsPath.valid:
            return

        path = rSlash(bpath)
        categories = self.getCategories()

        for cat in categories:
            if category and cat != category:
                continue

            if self.isInCategory(cat, path):
                marks = self.getCategoryMarks(cat)
                if not marks:
                    continue

                if delete is True:
                    del marks[path]
                    self.markDeleted.emit(path)
                    self.changed.emit()
                    continue

                return IPFSHashMark.fromJson(path, marks[path])

    def search(
            self,
            bpath,
            category=None,
            tags=[],
            delete=False):
        path = rSlash(bpath)
        categories = self.getCategories()

        for cat in categories:
            if category and cat != category:
                continue

            marks = self.getCategoryMarks(cat)
            if not marks:
                continue

            if path in marks.keys():
                if delete is True:
                    del marks[path]
                    self.markDeleted.emit(path)
                    self.changed.emit()
                    return True

                tagsOk = True
                m = marks[path]
                for stag in tags:
                    if stag not in m['tags']:
                        tagsOk = False

                if tagsOk:
                    return (path, marks[path])

    def insertMark(self, mark, category):
        # Insert a mark in given category, checking of already existing mark
        # is left to the caller
        sec = self.enterCategory(category, create=True)
        if not sec:
            return False

        # Handle IPFSHashMark or tuple
        if isinstance(mark, IPFSHashMark):
            if mark.path in sec[marksKey]:
                eMark = sec[marksKey][mark.path]

                if 'icon' in mark.markData:
                    eMark['icon'] = mark.markData['icon']
                return False
            sec[marksKey].update(mark)
            self.markAdded.emit(mark.path, mark.markData)
        else:
            try:
                mPath, mData = mark
                if mPath in sec[marksKey]:
                    # Patch some fields if already exists
                    eMark = sec[marksKey][mPath]
                    if 'icon' in mData:
                        eMark['icon'] = mData['icon']
                    return False
                sec[marksKey][mPath] = mData
                self.markAdded.emit(mPath, mData)
            except Exception:
                return False

        self.changed.emit()
        return True

    def add(self, bpath, title=None, category='general', share=False, tags=[],
            description=None, icon=None, pinSingle=False, pinRecursive=False):
        if not bpath:
            return None

        path = rSlash(bpath)

        sec = self.enterCategory(category, create=True)

        if not sec:
            return False

        if self.search(path):
            # We already have stored a mark with this path
            return False

        mark = IPFSHashMark.make(path,
                                 title=title,
                                 share=share,
                                 tags=tags,
                                 description=description,
                                 icon=icon,
                                 pinSingle=pinSingle,
                                 pinRecursive=pinRecursive
                                 )

        sec[marksKey].update(mark)
        self.changed.emit()
        self.markAdded.emit(path, mark.markData)

        return True

    def delete(self, path):
        return self.search(path, delete=True)

    def merge(self, oMarks, share=None, reset=False):
        count = 0
        for cat in oMarks.getCategories():
            marks = oMarks.getCategoryMarks(cat)
            for mark in marks.items():
                try:
                    mPath, mData = mark
                    if share is True and mData['share'] is False:
                        continue

                    if 'pin' in mData and reset:
                        mDataNew = copy.copy(mData)
                        mDataNew['pin']['single'] = False
                        mDataNew['pin']['recursive'] = False
                        mDataNew['share'] = False
                        self.insertMark((mPath, mDataNew), cat)
                    else:
                        self.insertMark(mark, cat)
                    count += 1
                except:
                    continue
        self.changed.emit()
        return count

    def follow(self, ipnsp, name, active=True, maxentries=4096,
               resolveevery=3600, share=False, autoPin=False):
        if ipnsp is None:
            return

        feedsSec = self._rootFeeds
        ipnsp = rSlash(ipnsp)

        if ipnsp in feedsSec:
            return
        feedsSec[ipnsp] = {
            'name': name,
            'active': active,
            'maxentries': maxentries,
            'resolvepolicy': 'auto',
            'resolveevery': resolveevery,
            'resolvedlast': None,
            'share': share,
            'autopin': autoPin,
            marksKey: {},
        }
        self.changed.emit()
        return feedsSec[ipnsp]

    def feedAddMark(self, ipnsp, mark):
        feeds = self._rootFeeds
        if ipnsp not in feeds:
            return False
        feed = feeds[ipnsp]
        sec = feed[marksKey]
        if mark.path in sec:
            return False

        sec.update(mark)
        self.feedMarkAdded.emit(feed['name'], mark)
        self.changed.emit()
        return True

    def getFeeds(self):
        return list(self._rootFeeds.items())

    def getFeedMarks(self, path):
        feeds = self.getFeeds()
        for fPath, fData in feeds:
            if fPath == path:
                return fData[marksKey]

    def serialize(self, fd):
        return json.dump(self._root, fd, indent=4, cls=MarksEncoder)

    def dump(self):
        print(self.serialize(sys.stdout))

    def norm(self, path):
        return path.rstrip('/')

    def pyramidPathFormat(self, category, name):
        return os.path.join(category, name)

    def pyramidGetLatestHashmark(self, pyramidPath):
        pyramid = self.pyramidGet(pyramidPath)
        if not pyramid:
            return None

        if pyramid.marksCount > 0:
            try:
                latest = pyramid.marks[-1]
                (mPath, mark), = latest.items()
                return IPFSHashMark.fromJson(mPath, mark)
            except:
                return None

    def onPyramidCapstone(self, pyramidPath):
        pyramid = self.pyramidGet(pyramidPath)
        latest = pyramid.latest

        if latest:
            mark = self.pyramidGetLatestHashmark(pyramidPath)
            if mark:
                self.pyramidNeedsPublish.emit(pyramidPath, mark)

    def pyramidNew(self, name, category, icon, description=None, ipnskey=None,
                   lifetime='48h'):
        sec = self.enterCategory(category, create=True)

        if not sec:
            return False

        if pyramidsKey not in sec:
            # Update the schema
            sec[pyramidsKey] = {}

        if name not in sec[pyramidsKey]:
            pyramid = MultihashPyramid.make(
                name, description=description,
                ipnskey=ipnskey, icon=icon,
                lifetime=lifetime,
                flags=MultihashPyramid.FLAG_MODIFIABLE_BYUSER
            )
            sec[pyramidsKey].update(pyramid)
            self.pyramidConfigured.emit(self.pyramidPathFormat(category, name))
            self.changed.emit()
            return sec[pyramidsKey][name]

    def pyramidAccess(self, pyramidPath):
        category = os.path.dirname(pyramidPath)
        name = os.path.basename(pyramidPath)
        sec = self.enterCategory(category, create=False)
        if sec:
            if pyramidsKey not in sec:
                # Update the schema
                sec[pyramidsKey] = {}
            return sec, category, name
        return None, None, None

    def pyramidGet(self, pyramidPath):
        sec, category, name = self.pyramidAccess(pyramidPath)
        if not sec:
            return None

        if name in sec[pyramidsKey]:
            pyramid = sec[pyramidsKey][name]
            _p = MultihashPyramid({name: pyramid})
            _p.name = name
            _p.path = pyramidPath
            return _p

    def pyramidDrop(self, pyramidPath):
        sec, category, name = self.pyramidAccess(pyramidPath)

        if not sec or pyramidsKey not in sec:
            return

        if name in sec[pyramidsKey]:
            del sec[pyramidsKey][name]
            self.changed.emit()

    def pyramidAdd(self, pyramidPath, path):
        path = self.norm(path)
        sec, category, name = self.pyramidAccess(pyramidPath)

        if not sec:
            return False

        if name in sec[pyramidsKey]:
            pyramid = sec[pyramidsKey][name]
            count = len(pyramid[pyramidsMarksKey])
            exmark = self.find(path)

            if exmark:
                mark = copy.copy(exmark)
            else:
                datenowiso = datetime.now().isoformat()
                mark = IPFSHashMark.make(path,
                                         title='{0}: #{1}'.format(
                                             name, count + 1),
                                         description=pyramid['description'],
                                         datecreated=datenowiso,
                                         share=False,
                                         pinSingle=True,
                                         icon=pyramid['icon'],
                                         )
            pyramid[pyramidsMarksKey].append(mark.data)
            pyramid['latest'] = path

            self.pyramidAddedMark.emit(pyramidPath, mark)
            self.pyramidChanged.emit(pyramidPath)
            self.pyramidCapstoned.emit(pyramidPath)
            self.changed.emit()

            return True

        return False

    def pyramidPop(self, pyramidPath):
        # Pop a hashmark off the list and republish

        pyramid = self.pyramidGet(pyramidPath)
        if not pyramid:
            return False

        if pyramid.marksCount > 0:
            pyramid.marks.pop()

            # Republish if there's a hashmark available
            mark = self.pyramidGetLatestHashmark(pyramidPath)
            if mark:
                pyramid.latest = mark.path
                self.pyramidNeedsPublish.emit(pyramidPath, mark)
            else:
                pyramid.latest = None

            self.pyramidChanged.emit(pyramidPath)

            if pyramid.empty:
                self.pyramidEmpty.emit(pyramidPath)

            self.changed.emit()
            return True

    async def pyramidsInit(self):
        categories = self.getCategories()
        for cat in categories:
            await asyncio.sleep(0)

            sec = self.enterCategory(cat)
            if not sec or pyramidsKey not in sec:
                continue

            pyramids = sec[pyramidsKey]
            for name, pyramid in pyramids.items():
                await asyncio.sleep(0)
                self.pyramidConfigured.emit(self.pyramidPathFormat(cat, name))
