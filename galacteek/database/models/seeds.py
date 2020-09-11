from tortoise.models import Model
from tortoise import fields


class IPSeed(Model):
    id = fields.IntField(pk=True)

    dagCid = fields.CharField(max_length=512, unique=True)
    dateAdded = fields.DatetimeField(auto_now_add=True)
    hidden = fields.BooleanField(default=False)
    status = fields.IntField(default=0)


OBJ_STATUS_QUEUED = 0
OBJ_STATUS_ERROR = 1
OBJ_STATUS_FINISHED = 2
OBJ_STATUS_PAUSED = 3
OBJ_STATUS_CANCELLED = 4


class IPSeedObject(Model):
    id = fields.IntField(pk=True)

    # The DAG object index inside the seed's objects list
    objIndex = fields.IntField(default=0)

    # PIN-related fields
    pin = fields.BooleanField(default=True)
    pinned = fields.BooleanField(default=False)
    pinnedDate = fields.DatetimeField(null=True, auto_now_add=False)
    pinnedNodesCur = fields.IntField(default=0)
    pinnedNodesFinal = fields.IntField(default=0)
    pinStatus = fields.IntField(default=0)

    # Download-related fields
    download = fields.BooleanField(default=False)
    downloaded = fields.BooleanField(default=False)
    downloadedDate = fields.DatetimeField(null=True, auto_now_add=False)
    downloadedTo = fields.CharField(null=True, max_length=1024, unique=True)
    downloadStatus = fields.IntField(default=0)
    downloadChunkSize = fields.IntField(default=524288)

    # General status
    status = fields.IntField(default=0)

    ignore = fields.BooleanField(default=False)
    pubsubNotify = fields.BooleanField(default=False)

    # Foreign key
    seed = fields.ForeignKeyField(
        'models.IPSeed',
        related_name='seed',
        through='ipseed_object')
