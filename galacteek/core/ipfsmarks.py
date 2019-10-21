import json
import time
import sys
import collections
import copy
import re
import os.path
import asyncio
import uuid
from datetime import datetime

from jsonschema import validate
from jsonschema.exceptions import ValidationError

import aiofiles

from galacteek import log
from galacteek.core import utcDatetimeIso
from galacteek.core import parseDate
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import normpPreserve

from PyQt5.QtCore import pyqtSignal, QObject


class MarksEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, IPFSHashMark):
            return obj.data
        return json.JSONEncoder.default(self, obj)


marksKey = '_marks'
pyramidsKey = '_pyramids'
pyramidsMarksKey = '_pyramidmarks'
pyramidMaxHmarksDefault = 16


def categoryValid(category):
    return re.match('^([0-9A-Za-z-_/]+)$', category) is not None


ppRe = r"^(/(ipfs|ipns)/[\w<>\:\;\,\?\!\*\%\&\=\@\$\~/\s\.\-_\\\'\(\)\+]{1,1024}$)"  # noqa

hashmarkSchema = {
    "title": "Hashmark",
    "description": "Hashmark object",
    "type": "object",
    "patternProperties": {
        ppRe: {
            "properties": {
                "metadata": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"}
                    },
                    "required": ["title", "description"]
                },
                "datecreated": {"type": "string"},
                "tags": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    }
                }
            },
            "required": ["metadata", "datecreated", "tags"]
        }
    }
}


hashmarksSchema = {
    "title": "Hashmarks",
    "description": "Hashmarks collection",
    "type": "object",
    "properties": {
        "ipfsmarks": {
            "type": "object",
            "properties": {
                "categories": {
                    "$ref": "#/definitions/category"
                }
            }
        }
    },
    "definitions": {
        "category": {
            "type": "object",
            "patternProperties": {
                r"^_marks$": hashmarkSchema,
                r"^_{0}[\w0-9]{1,128}": {
                    "$ref": "#/definitions/category"
                }
            }
        }
    }
}


class IPFSHashMark(collections.UserDict):
    @property
    def markData(self):
        return self.data[self.path]

    @property
    def metadata(self):
        return self.markData['metadata']

    @property
    def title(self):
        return self.metadata['title']

    @property
    def description(self):
        return self.metadata['description']

    @property
    def comment(self):
        return self.metadata['comment']

    @property
    def datecreated(self):
        return self.markData['datecreated']

    @property
    def dtCreated(self):
        return parseDate(self.datecreated)

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

    def isValid(self):
        try:
            validate(self.data, hashmarkSchema)
        except ValidationError as verr:
            log.debug('Invalid JSON schema error: {}'.format(str(verr)))
            return False
        else:
            return True

    @staticmethod
    def fromJson(mPath, metadata):
        if not IPFSPath(mPath).valid or not isinstance(metadata, dict):
            return None

        hmark = IPFSHashMark({mPath: metadata})
        hmark.path = mPath
        return hmark

    @staticmethod
    def make(path, title=None, datecreated=None, share=False,
             description='', comment='', datasize=None, cumulativesize=None,
             srcplanet='Earth', tags=None,
             numlinks=None, icon=None, pinSingle=False, pinRecursive=False):
        if datecreated is None:
            datecreated = utcDatetimeIso()

        mData = IPFSHashMark({
            path: {
                'metadata': {
                    'title': title,
                    'description': description,
                    'comment': comment,
                    'srcplanet': srcplanet,
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
                'icon': icon,
                'share': share,
                'tags': tags if tags else [],
            }
        })

        mData.path = path
        return mData


class MultihashPyramid(collections.UserDict):
    # Types
    TYPE_STANDARD = 0

    TYPE_GALLERY = 1

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
    def type(self):
        return self.p['type']

    @property
    def uuid(self):
        return self.p['uuid']

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

    @property
    def maxHashmarks(self):
        return self.p.get('maxhashmarks', pyramidMaxHmarksDefault)

    @staticmethod
    def make(name, description='Pyramid', icon=None, ipnskey=None,
             internal=False, publishdelay=0, comment=None, flags=0,
             allowoffline=True, lifetime='48h',
             maxhashmarks=pyramidMaxHmarksDefault,
             type=None):
        datecreated = utcDatetimeIso()
        pyramid = MultihashPyramid({
            name: {
                'ipns': {
                    'publishtokey': ipnskey,
                    'publishdelay': publishdelay,
                    'allowoffline': allowoffline,
                    'ttl': None,
                    'lifetime': lifetime
                },
                'uuid': str(uuid.uuid4()),
                'datecreated': datecreated,
                'icon': icon,
                'latest': None,
                'description': description,
                'comment': comment,
                'type': type if type else MultihashPyramid.TYPE_STANDARD,
                'internal': internal,
                'maxhashmarks': maxhashmarks,
                'flags': flags,
                pyramidsMarksKey: []  # list of hashmarks in the pyramid
            }
        })

        pyramid.name = name
        return pyramid


class QuickAccessMapping(collections.UserDict):
    """
    Mapping for the q:// scheme
    """

    @property
    def name(self):
        return self.data['name']

    @property
    def title(self):
        return self.data['title']

    @property
    def path(self):
        return self.data['mappedto']

    @property
    def ipnsFreq(self):
        return self.data['ipnsresolvefreq']

    @staticmethod
    def make(name, ipfsMPath, title=None,
             ipnsResolveFrequency=3600):
        datecreated = utcDatetimeIso()
        mapping = QuickAccessMapping({
            'name': name,
            'mappedto': str(ipfsMPath),
            'ipnsresolvefreq': ipnsResolveFrequency,
            'datecreated': datecreated,
            'hotkey': None,
            'title': title if title else name
        })
        return mapping


class IPFSMarks(QObject):
    changed = pyqtSignal()
    markDeleted = pyqtSignal(str, str)
    markAdded = pyqtSignal(str, dict)
    feedMarkAdded = pyqtSignal(str, IPFSHashMark)

    pyramidConfigured = pyqtSignal(str)
    pyramidAddedMark = pyqtSignal(str, IPFSHashMark)
    pyramidCapstoned = pyqtSignal(str)
    pyramidNeedsPublish = pyqtSignal(str, IPFSHashMark)
    pyramidChanged = pyqtSignal(str)
    pyramidEmpty = pyqtSignal(str)

    def __init__(self, path, parent=None, data=None, autosave=True,
                 backup=False):
        super().__init__(parent)

        self._path = path
        self._autosave = autosave
        self._backup = backup
        self._marks = data if data else self.load()
        self.changed.connect(self.onChanged)
        self.lastsaved = None
        self.changed.emit()

        self.pyramidCapstoned.connect(self.onPyramidCapstone)

    @property
    def path(self):
        return self._path

    @property
    def autosave(self):
        return self._autosave

    @property
    def backup(self):
        return self._backup

    @property
    def root(self):
        return self._marks

    @property
    def _rootMarks(self):
        return self.root['ipfsmarks']

    @property
    def _rootCategories(self):
        return self._rootMarks['categories']

    @property
    def _rootFeeds(self):
        return self.root['feeds']

    @property
    def _rootQMappings(self):
        return self.root['qamappings']

    def skeleton(self):
        return {
            'uuid': str(uuid.uuid4()),
            'ipfsmarks': {
                'categories': {}
            },
            'feeds': {},
            'qamappings': []
        }

    def load(self):
        if not self.path:
            return self.skeleton()
        try:
            with open(self.path, 'rt') as fd:
                marks = json.load(fd)

            if 'qamappings' not in marks:
                marks['qamappings'] = []

            if 'uuid' not in marks:
                marks['uuid'] = str(uuid.uuid4())

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
        except BaseException:
            log.debug('Could not save hashmarks ({0}'.format(
                self.path))
        else:
            if not self.backup:
                return

            now = time.time()
            if not self.lastsaved or (now - self.lastsaved) > (60 * 5):
                bkpPath = '{0}.bkp'.format(self.path)

                try:
                    with open(bkpPath, 'w+t') as fd:
                        self.serialize(fd)
                except:
                    log.debug('Could not save backup file {0}'.format(bkpPath))
                else:
                    log.debug('Hashmarks backup saved: {}'.format(bkpPath))

            self.lastsaved = now

    async def saveAsync(self):
        async with aiofiles.open(self.path, 'w+t') as fd:
            await fd.write(json.dumps(self.root, indent=4, cls=MarksEncoder))
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

        return sorted(list(_list([], parent=self._rootCategories)))

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
            spath = path.rstrip('/')
            return spath in sec[marksKey] or spath + '/' in sec[marksKey]

    def getCategoryMark(self, marks, path):
        unslashed = path.rstrip('/')
        slashed = unslashed + '/'
        if unslashed in marks:
            return IPFSHashMark.fromJson(unslashed, marks[unslashed])
        elif slashed in marks:
            return IPFSHashMark.fromJson(slashed, marks[slashed])

    def getAll(self, share=False):
        cats = self.getCategories()
        _all = {}
        for cat in cats:
            catMarks = self.getCategoryMarks(cat)
            for mpath, mark in catMarks.items():
                if mark['share'] == share:
                    _all[mpath] = mark
        return _all

    def isValid(self):
        try:
            validate(self.root, hashmarksSchema)
        except ValidationError as verr:
            log.debug(
                'Hashmarks collection: invalid JSON schema error: {}'.format(
                    str(verr)))
            return False
        else:
            log.debug('Hashmarks collection: valid JSON schema !')
            return True

    async def isValidAsync(self):
        # Run JSON schema validation in an executor
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.isValid)

    async def searchAllByMetadata(self, metadata):
        # todo: deprecate searchSingleByMetadata
        if not isinstance(metadata, dict):
            raise ValueError('Metadata needs to be a dictionary')

        categories = self.getCategories()

        title = metadata.get('title')
        descr = metadata.get('description')
        path = metadata.get('path')
        comment = metadata.get('comment')

        def metaMatch(mark, field, searchQuery):
            if field not in mark['metadata'] or not isinstance(
                    mark['metadata'][field], str):
                return

            comps = searchQuery.split()
            if len(comps) == 1:
                if re.search(searchQuery, mark['metadata'][field],
                             re.IGNORECASE):
                    return True
                else:
                    return False
            else:
                lowered = mark['metadata'][field].lower()
                for comp in comps:
                    try:
                        lowered.index(comp)
                    except:
                        return False

                return True

        for cat in categories:
            await asyncio.sleep(0)

            marks = self.getCategoryMarks(cat)
            if not marks:
                continue

            for mPath, mark in marks.items():
                if not isinstance(mPath, str):
                    continue

                if 'metadata' not in mark:
                    continue

                # Remove root prefix or you'd end up with a
                # lot of stuff when searching for 'ipfs' or 'ipns'
                mPathClear = mPath.replace(
                    '/ipfs/', '').replace('/ipns/', '')

                if path and re.search(path, mPathClear):
                    yield IPFSHashMark.fromJson(mPath, mark)
                    await asyncio.sleep(0)
                    continue

                if title and metaMatch(mark, 'title', title):
                    yield IPFSHashMark.fromJson(mPath, mark)
                    await asyncio.sleep(0)
                    continue

                if descr and metaMatch(mark, 'description', descr):
                    yield IPFSHashMark.fromJson(mPath, mark)
                    await asyncio.sleep(0)
                    continue

                if comment and metaMatch(mark, 'comment', comment):
                    yield IPFSHashMark.fromJson(mPath, mark)
                    await asyncio.sleep(0)
                    continue

    def searchSingleByMetadata(self, metadata):
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

    def find(self, mpath, category=None, delete=False):
        path = normpPreserve(mpath)
        if not IPFSPath(path).valid:
            return

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
                    self.markDeleted.emit(cat, path)
                    self.changed.emit()
                    return True

                return self.getCategoryMark(marks, path)

    def insertMark(self, mark, category):
        # Insert a mark in given category, checking of already existing mark
        # is left to the caller
        sec = self.enterCategory(category, create=True)
        if not sec:
            return False

        # Handle IPFSHashMark or tuple
        if isinstance(mark, IPFSHashMark):
            if not mark.isValid():
                return False

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

    def add(self, mpath, title=None, category='general', share=False, tags=[],
            description=None, icon=None, pinSingle=False, pinRecursive=False):
        if not mpath:
            return False

        iPath = IPFSPath(normpPreserve(mpath))
        if not iPath.valid:
            return False

        path = str(iPath)

        sec = self.enterCategory(category, create=True)

        if not sec:
            return False

        if self.find(path):
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
        return self.find(path, delete=True)

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
        ipnsp = normpPreserve(ipnsp)

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
        return json.dump(self.root, fd, indent=4, cls=MarksEncoder)

    def dump(self):
        print(self.serialize(sys.stdout))

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
                   lifetime='48h', type=MultihashPyramid.TYPE_STANDARD):
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
                flags=MultihashPyramid.FLAG_MODIFIABLE_BYUSER,
                type=type
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
        sec, category, name = self.pyramidAccess(pyramidPath)

        if not sec:
            return False

        if name in sec[pyramidsKey]:
            pyramid = sec[pyramidsKey][name]
            count = len(pyramid[pyramidsMarksKey])

            if count >= pyramid.get('maxhashmarks', pyramidMaxHmarksDefault):
                pyramid[pyramidsMarksKey].pop(0)

            exmark = self.find(path)

            if exmark:
                mark = copy.copy(exmark)
            else:
                datenowiso = utcDatetimeIso()
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

    def qaMap(self, name, mappedTo, title=None, ipnsResolveFrequency=3600):
        for m in self.qaGetMappings():
            if m.name == name:
                return False

        mapping = QuickAccessMapping.make(
            name, mappedTo, title=title,
            ipnsResolveFrequency=ipnsResolveFrequency)
        self._rootQMappings.append(mapping.data)
        self.changed.emit()
        return True

    def qaGetMappings(self):
        return [QuickAccessMapping(m) for m in copy.copy(self._rootQMappings)]
