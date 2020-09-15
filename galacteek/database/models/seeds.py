from tortoise.models import Model
from tortoise import fields


class IPSeed(Model):
    id = fields.IntField(pk=True)

    dagCid = fields.CharField(max_length=1024, unique=True)
    status = fields.IntField(default=0)


OBJ_STATUS_QUEUED = 0
OBJ_STATUS_ERROR = 1
OBJ_STATUS_FINISHED = 2


class IPSeedObject(Model):
    id = fields.IntField(pk=True)

    objIndex = fields.IntField(default=0)
    status = fields.IntField(default=0)

    pin = fields.BooleanField(default=True)
    pinned = fields.BooleanField(default=False)
    pinnedDate = fields.DatetimeField(null=True, auto_now_add=False)

    download = fields.BooleanField(default=False)
    downloaded = fields.BooleanField(default=False)
    downloadedDate = fields.DatetimeField(null=True, auto_now_add=False)
    downloadedTo = fields.CharField(null=True, max_length=1024, unique=True)

    status = fields.IntField(default=0)

    seed = fields.ForeignKeyField(
        'models.IPSeed',
        related_name='seed',
        through='ipseed_object')
