from tortoise.models import Model
from tortoise import fields

from galacteek.ipfs.cidhelpers import IPFSPath


class Hashmark(Model):
    PIN_NO = 0
    PIN_SINGLE = 1
    PIN_RECURSIVE = 2

    id = fields.IntField(pk=True)

    path = fields.CharField(max_length=1024, null=True,
                            description='IPFS object path')
    url = fields.CharField(null=True, max_length=1024,
                           description='URL for non-IPFS (ENS, ..) hashmarks')

    # Metadata
    title = fields.CharField(max_length=128, null=True,
                             description='Hashmark title')
    description = fields.CharField(max_length=512, null=True,
                                   description='Hashmark description')
    comment = fields.CharField(max_length=1024, null=True,
                               description='Comment')

    # Category
    category = fields.ForeignKeyField(
        'models.Category',
        related_name='category',
        through='hashmark_category',
        null=True,
        description='Category')

    # Hashmark source
    source = fields.ForeignKeyField(
        'models.HashmarkSource',
        related_name='source',
        through='hashmark_source',
        description='Source associated with the hashmark')

    # Creator
    creator = fields.ForeignKeyField(
        'models.DwebNetizen',
        related_name='creator',
        null=True,
        through='hashmark_creator',
        description='Hashmark creator')

    # app = fields.ForeignKeyField(
    #    'models.HashmarkApp',
    #    related_name='app',
    #    through='hashmark_app')

    schemepreferred = fields.CharField(
        max_length=32,
        null=True,
        description='Preferred URL scheme to use when opening this object')

    parent: fields.ForeignKeyNullableRelation['Hashmark'] = \
        fields.ForeignKeyField(
        'models.Hashmark', related_name='parentrelation', null=True)
    parentrelation: fields.ReverseRelation['Hashmark']

    icon: fields.ForeignKeyNullableRelation['Hashmark'] = \
        fields.ForeignKeyField(
        'models.Hashmark', related_name='iconrelaton', null=True)
    iconrelation: fields.ReverseRelation['Hashmark']

    # PIN (0: nopin, 1: single, 2: recursive)
    pin = fields.IntField(default=0)

    # Dates
    datecreated = fields.DatetimeField(auto_now_add=True,
                                       description='Hashmark creation date')
    datemodified = fields.DatetimeField(
        auto_now=True, description='Hashmark modification date')
    lastvisited = fields.DatetimeField(null=True,
                                       description='Last visited date')

    # Object size metadata
    cumulativesize = fields.IntField(
        null=True, description='Total IPFS object size')
    numlinks = fields.IntField(
        null=True, description='IPFS links count')
    mimetype = fields.CharField(
        max_length=64, null=True, description='MIME type')

    visitcount = fields.IntField(
        default=0, description='Hashmark visit count')

    active = fields.BooleanField(
        default=True, description='Active/visible flag')
    share = fields.BooleanField(
        default=False, description='Share/broadcast this hashmark')
    sticky = fields.BooleanField(
        default=False, description='Sticky flag')
    follow = fields.BooleanField(
        default=False, description='IPNS follow')

    iptags = fields.ManyToManyField(
        'models.IPTag', related_name='iptags',
        through='hashmark_iptags',
        description='List of tags')
    objtags = fields.ManyToManyField(
        'models.IPTag', related_name='objtags',
        through='hashmark_objtags',
        description='List of object tags')

    @property
    def uri(self):
        return self.path if self.path else self.url

    async def _fetch_all(self):
        await self.fetch_related(
            'category', 'source', 'parent', 'icon',
            'iptags', 'objtags')

    def preferredUrl(self):
        if self.path:
            iPath = IPFSPath(self.path, autoCidConv=True)
            if self.schemepreferred == 'dweb':
                return iPath.dwebUrl
            elif not self.schemepreferred or self.schemepreferred in \
                    ['ipfs', 'ipns']:
                return iPath.ipfsUrl
        else:
            return self.url

    def __str__(self):
        return '{p}: {title} ({date})'.format(
            p=self.uri, title=self.title, date=self.datecreated
        )


class IPNSFeed(Model):
    id = fields.IntField(pk=True)

    name = fields.CharField(max_length=32, description='Feed name')
    active = fields.BooleanField(default=True)
    notify = fields.BooleanField(default=True)
    autopin = fields.BooleanField(default=True)
    maxentries = fields.IntField(default=0)
    resolvepolicy = fields.CharField(default='auto', max_length=16)
    resolveevery = fields.IntField(default=3600)
    resolvedlast = fields.DatetimeField(null=True)
    resolvenext = fields.DatetimeField(null=True)

    feedhashmark = fields.ForeignKeyField(
        'models.Hashmark',
        related_name='feedhashmark',
        through='ipnsfeed_hashmark')

    async def entries(self):
        await self.fetch_related('feedhashmark')
        return await Hashmark.filter(
            parent__id=self.feedhashmark.id
        )

    def __str__(self):
        return self.name


class DwebNetizen(Model):
    id = fields.IntField(pk=True)

    name = fields.CharField(max_length=64, null=True)
    did = fields.CharField(max_length=256, unique=True,
                           description='DID')


class HashmarkApp(Model):
    id = fields.IntField(pk=True)

    name = fields.CharField(max_length=64)
    descr = fields.CharField(max_length=128)


class QAObjTagItem(Model):
    id = fields.IntField(pk=True)

    tag = fields.CharField(max_length=64, unique=True,
                           description='IP object tag name')


class QAHashmarkItem(Model):
    id = fields.IntField(pk=True)

    ithashmark = fields.ForeignKeyField(
        'models.Hashmark',
        related_name='ithashmark',
        through='qaitem_hashmark')


class HashmarkQaMapping(Model):
    id = fields.IntField(pk=True)

    name = fields.CharField(max_length=32)
    ipnsresolvefreq = fields.IntField(default=3600)

    qahashmark = fields.ForeignKeyField(
        'models.Hashmark',
        related_name='qahashmark',
        through='mapping_hashmark')


class HashmarkSource(Model):
    TYPE_LOCAL = 0
    TYPE_PYMODULE = 1
    TYPE_GITREPOS = 2
    TYPE_IPFS = 3
    TYPE_IPFSMARKS_LEGACY = 4

    id = fields.IntField(pk=True)

    type = fields.IntField(default=TYPE_LOCAL)
    name = fields.CharField(max_length=64, unique=True, null=True)
    url = fields.CharField(max_length=256, null=True, unique=True)
    uid = fields.CharField(max_length=256, null=True, unique=True)
    syncedlast = fields.DatetimeField(null=True)

    author = fields.CharField(max_length=128, null=True)

    enabled = fields.BooleanField(default=True)
    flags = fields.IntField(default=0)

    def __str__(self):
        if self.type == HashmarkSource.TYPE_LOCAL:
            return 'Local source'
        elif self.type == HashmarkSource.TYPE_PYMODULE:
            return 'PyModule source: {0}'.format(self.name)
        elif self.type == HashmarkSource.TYPE_GITREPOS:
            return 'GIT source: {0} ({1})'.format(self.name, self.url)
        elif self.type == HashmarkSource.TYPE_IPFSMARKS_LEGACY:
            return 'IPFSMarks source: {0}'.format(self.name)
        else:
            return 'Unknown source'


class HashmarkSyncHistory(Model):
    id = fields.IntField(pk=True)

    srcsynccount = fields.IntField(
        default=0, description='Sources synced count')
    hashmarkstotal = fields.IntField(
        default=0, description='Total hashmarks in database after sync')
    hashmarksadded = fields.IntField(
        default=0, description='Added hashmarks count')
    date = fields.DatetimeField(auto_now_add=True)


class IPTag(Model):
    id = fields.IntField(pk=True)

    name = fields.CharField(
        max_length=32, description='IP Tag', unique=True)

    watch = fields.BooleanField(default=False)
    ignore = fields.BooleanField(default=False)
    priority = fields.IntField(default=0)

    revhashmarks = fields.ManyToManyField(
        'models.Hashmark', related_name='revhashmarks',
        through='iptag_hashmarks',
        description='List of hashmarks')

    def __str__(self):
        return self.name


class Category(Model):
    id = fields.IntField(pk=True)

    name = fields.CharField(max_length=32, description='Category name')

    active = fields.BooleanField(default=True)
    hidden = fields.BooleanField(default=False)

    def __str__(self):
        return self.name


class URLHistoryItem(Model):
    id = fields.IntField(pk=True)

    url = fields.CharField(max_length=1024, unique=True)
    scheme = fields.CharField(null=True, max_length=32)
    rootcid = fields.CharField(null=True, max_length=256)
    rootcidv = fields.IntField(default=0)
    datecreated = fields.DatetimeField(auto_now_add=True)

    # Metadata

    descr = fields.CharField(max_length=512, null=True)
    comment = fields.CharField(max_length=512, null=True)


class URLHistoryVisit(Model):
    id = fields.IntField(pk=True)

    title = fields.CharField(max_length=512, null=True)

    dateaccess = fields.DatetimeField(auto_now_add=True)

    historyitem = fields.ForeignKeyField(
        'models.URLHistoryItem',
        related_name='historyitem',
        through='urlhistoryvisit_item')
