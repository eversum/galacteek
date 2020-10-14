import traceback
import asyncio
import functools
from datetime import datetime
from datetime import timedelta

from tortoise import Tortoise
from tortoise.query_utils import Q
from tortoise.functions import Count

from PyQt5.QtCore import QUrl

from galacteek import log
from galacteek import AsyncSignal
from galacteek.core import iptags
from galacteek.core.asynclib import loopTime
from galacteek.ipfs.cidhelpers import IPFSPath


from galacteek.database.models import *

databaseLock = asyncio.Lock()


def dbLock(func):
    @functools.wraps(func)
    async def wrapper(*args, **kw):
        async with databaseLock:
            return await func(*args, **kw)

    return wrapper


async def initOrm(dbpath):
    log.debug('ORM init: {}'.format(dbpath))

    try:
        await Tortoise.init(
            db_url='sqlite://{}'.format(dbpath),
            modules={'models': ['galacteek.database.models']}
        )

        await Tortoise.generate_schemas()
    except Exception:
        traceback.print_exc()
        return False
    else:
        return True


async def closeOrm():
    await Tortoise.close_connections()


HashmarkAdded = AsyncSignal(Hashmark)
HashmarkDeleted = AsyncSignal(Hashmark)
IPNSFeedMarkAdded = AsyncSignal(IPNSFeed, Hashmark)


async def hashmarksAll():
    return await Hashmark.all()


async def hashmarksCount():
    return await Hashmark.all().count()


async def hashmarksByPath(ref):
    iPath = IPFSPath(ref, autoCidConv=True)
    return await Hashmark.filter(
        Q(path=str(iPath)) | Q(url=ref)).first()


async def hashmarksSearch(query=None, category=None):
    filter = Q(active=True)

    if query:
        filter = filter & (Q(path__icontains=query) |
                           Q(title__icontains=query) |
                           Q(description__icontains=query) |
                           Q(url__icontains=query))
    if category:
        filter = filter & Q(category__name=category)

    return await Hashmark.filter(filter)


async def hashmarksExists(pathorurl):
    return await hashmarksByPath(pathorurl) is not None


async def hashmarksByObjTagLatest(tag):
    tags = iptags.ipTagsFormatList([tag])

    return await Hashmark.filter(
        objtags__name__in=tags
    ).order_by('-datecreated').first()


async def hashmarksByTags(taglist, strict=False, limit=0, **kw):
    tags = iptags.ipTagsFormatList(taglist, **kw)

    filter = Q(iptags__name__in=tags)

    for tag in tags:
        if strict:
            filter = filter | Q(iptags__name=tag)
        else:
            filter = filter | Q(iptags__name__icontains=tag)

    return await Hashmark.filter(filter).limit(
        limit if limit > 0 else 32768)


async def hashmarksByObjTags(taglist, **kw):
    tags = iptags.ipTagsFormatList(taglist, **kw)

    filter = Q(objtags__name__in=tags)

    for tag in tags:
        filter = filter | Q(objtags__name__icontains=tag)

    return await Hashmark.filter(filter)


async def hashmarksPopularTags(min=1, limit=64):
    return await IPTag.annotate(
        marks_count=Count('revhashmarks')).filter(
            marks_count__gte=min).limit(limit).order_by('-marks_count')


async def hashmarkDelete(path: str):
    if not await hashmarksExists(path):
        return False

    mark = await hashmarksByPath(path)
    if mark:
        await HashmarkDeleted.emit(mark)
        await mark.delete()


async def hashmarkTagsUpdate(hashmark, tagsl: list, type='iptags'):
    tags = iptags.ipTagsFormatList(tagsl)
    for tag in tags:
        if not isinstance(tag, str):
            continue

        itag = await ipTagAdd(tag)

        if type == 'iptags':
            await hashmark.iptags.add(itag)
            await itag.revhashmarks.add(hashmark)
        elif type == 'objtags':
            await hashmark.objtags.add(itag)


async def hashmarkAdd(path: str,
                      title='No title',
                      description=None,
                      comment=None,
                      category=None,
                      icon=None,
                      tags=None,
                      objtags=None,
                      parent=None,
                      pin=Hashmark.PIN_NO,
                      share=False,
                      datecreated=None,
                      source=None,
                      **kw):

    mark = await hashmarksByPath(path)
    if mark:
        return mark

    mark = await hashmarksByPath(path.rstrip('/'))
    if mark:
        return mark

    if source is None:
        source = await hashmarkSourceLocal()

    extra = {}

    if datecreated:
        extra['datecreated'] = datecreated

    if category:
        cat = await Category.filter(name=category).first()

        if not cat:
            cat = Category(name=category)
            await cat.save()

        extra['category'] = cat

    extra.update(**kw)

    ipfsPath = IPFSPath(path, autoCidConv=True)
    if ipfsPath.valid:
        extra['path'] = str(ipfsPath)
        extra['url'] = ipfsPath.ipfsUrl
    else:
        url = QUrl(path)
        if url.isValid() and url.scheme() in ['ens', 'ensr']:
            extra['url'] = url.toString()

    if isinstance(icon, str):
        path = IPFSPath(icon, autoCidConv=True)
        if path.valid:
            icon = await iconGet(str(path))

    mark = Hashmark(title=title,
                    description=description,
                    comment=comment,
                    icon=icon,
                    source=source,
                    parent=parent,
                    pin=pin,
                    share=share,
                    **extra)
    await mark.save()

    if isinstance(tags, list):
        await hashmarkTagsUpdate(mark, tags)

    if isinstance(objtags, list):
        await hashmarkTagsUpdate(mark, objtags, type='objtags')

    await HashmarkAdded.emit(mark)
    return mark


async def hashmarkMappingAdd(name, title, path, ipnsresolvefreq=3600):
    mark = await hashmarksByPath(path)
    if not mark:
        mark = await hashmarkAdd(path, title=title)

    if await HashmarkQaMapping.filter(name=name).first():
        return None

    m = HashmarkQaMapping(name=name, qahashmark=mark)
    await m.save()
    return m


async def hashmarkMappingsAll():
    return await HashmarkQaMapping.all()


async def ipTagsAll():
    return await IPTag.all()


async def categoriesNames():
    cats = await Category.all()
    return [c.name for c in cats]


async def hashmarkSourceSearch(name=None, type=0, url=None):
    filter = Q(type=type)

    if name:
        filter = filter & Q(name=name)

    if url:
        filter = filter & Q(url=url)

    return await HashmarkSource.filter(filter).first()


async def hashmarkSourceAll():
    return await HashmarkSource.all()


async def hashmarkSourceAdd(type, url, name=None):
    if not await hashmarkSourceSearch(url=url, type=type):
        source = HashmarkSource(name=name, type=type, url=url)
        await source.save()


async def hashmarkSourceLocal(name='local'):
    src = await HashmarkSource.filter(name=name).first()
    if not src:
        src = HashmarkSource(name=name, type=HashmarkSource.TYPE_LOCAL)
        await src.save()

    return src


async def ipTagGet(tag):
    return await IPTag.filter(name=tag).first()


async def ipTagAdd(tag):
    ex = await ipTagGet(tag)
    if not ex:
        itag = IPTag(name=tag)
        await itag.save()
        return itag
    return ex


async def urlHistorySearch(query):
    return await URLHistoryVisit.filter(
        Q(historyitem__url__icontains=query) |
        Q(title__icontains=query)).order_by(
            '-dateaccess').distinct().values(
            'title',
            url='historyitem__url'
    )


async def urlHistoryGet(url):
    return await URLHistoryItem.filter(url=url).first()


async def urlHistoryRecord(url, title):
    from galacteek.core.schemes import isIpfsUrl

    item = await urlHistoryGet(url)

    if not item:
        qUrl = QUrl(url)
        scheme = qUrl.scheme() if qUrl.isValid() else ''

        rootcid = ''
        rootcidv = 0

        if isIpfsUrl(qUrl):
            ipfsPath = IPFSPath(url)
            if ipfsPath.valid and ipfsPath.rootCid:
                rootcid = str(ipfsPath.rootCid)
                rootcidv = ipfsPath.rootCid.version

        item = URLHistoryItem(
            url=url, rootcid=rootcid, rootcidv=rootcidv,
            scheme=scheme)
        await item.save()

    visit = URLHistoryVisit(historyitem=item, title=title)
    await visit.save()

    return item, visit


async def urlHistoryClear():
    await URLHistoryVisit.filter().all().delete()
    await URLHistoryItem.filter().all().delete()


async def qaTagItems():
    return await QAObjTagItem.all()


async def qaHashmarkItems():
    return await QAHashmarkItem.all().prefetch_related('ithashmark')


QATagItemConfigured = AsyncSignal(QAObjTagItem)


async def qaTagItemAdd(tag):
    item = await QAObjTagItem.filter(tag=tag).first()
    if not item:
        item = QAObjTagItem(tag=tag)
        await item.save()

    await QATagItemConfigured.emit(item)


async def iconGetOld(path):
    icon = await DwebIcon.filter(path=path).first()
    if not icon:
        icon = DwebIcon(path=path)
        await icon.save()

    return icon


async def iconGet(path):
    icon = await Hashmark.filter(path=path).first()
    if not icon:
        icon = await hashmarkAdd(
            path,
            tags=['#dwebicon'],
            pin=Hashmark.PIN_SINGLE
        )
        await icon.save()

    return icon


async def hashmarkSourcesNeedSync(minutes=60):
    now = datetime.now()
    maxdate = now - timedelta(minutes=minutes)

    filter = Q(type__in=[
        HashmarkSource.TYPE_GITREPOS,
        HashmarkSource.TYPE_IPFSMARKS_LEGACY,
        HashmarkSource.TYPE_PYMODULE
    ])

    return await HashmarkSource.filter(
        filter & (Q(syncedlast__lt=maxdate) | Q(syncedlast__isnull=True))
    ).order_by('-syncedlast')


async def ipnsFeedsNeedSync(minutes=10):
    now = datetime.now()
    maxdate = now - timedelta(minutes=minutes)

    filter = Q(active=True) & \
        (Q(resolvenext__lt=maxdate) | Q(resolvenext__isnull=True))

    return await IPNSFeed.filter(filter).order_by('-resolvedlast')


async def seedAdd(cid: str):
    seed = IPSeed(dagCid=cid)
    await seed.save()
    return seed


async def seedGet(cid: str):
    return await IPSeed.filter(dagCid=cid).first()


async def seedDelete(cid: str):
    try:
        await IPSeed.filter(dagCid=cid).first().delete()
        return True
    except Exception:
        return False


async def seedGetObject(seed, objIdx: int):
    return await IPSeedObject.filter(
        seed__dagCid=seed.dagCid, objIndex=objIdx).first()


async def seedConfigObject(seed, objIdx: int, pin=True, download=False):
    obj = await seedGetObject(seed, objIdx)
    if not obj:
        obj = IPSeedObject(
            seed=seed, objIndex=objIdx, pin=pin, download=download)
        await obj.save()
    else:
        obj.pin = pin
        obj.download = download
        await obj.save()


async def seedsAll():
    return await IPSeed.all()


# Pub chat tokens


async def pubChatTokenNew(cid, channel, secTopic, peerId, **kw):
    try:
        token = PubChatSessionToken(
            cid=cid, channel=channel, secTopic=secTopic,
            peerId=peerId,
            ltLast=loopTime(),
            **kw)
        await token.save()
        return token
    except Exception:
        return None


async def pubChatTokenGet(cid):
    return await PubChatSessionToken.filter(cid=cid).first()


async def pubChatTokensClear():
    await PubChatSessionToken.all().delete()


async def pubChatTokenDelete(cid):
    return await PubChatSessionToken.filter(cid=cid).delete()


async def pubChatTokensByChannel(channel):
    return await PubChatSessionToken.filter(channel=channel).all()


async def pubChatTokensInactive(ltMax):
    return await PubChatSessionToken.filter(ltLast__lt=ltMax).all()
