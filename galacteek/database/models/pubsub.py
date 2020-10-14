from tortoise.models import Model
from tortoise import fields


class PubSubChannel(Model):
    ENCTYPE_JSON = 0

    id = fields.IntField(pk=True)

    topic = fields.CharField(max_length=512, unique=True)
    encType = fields.IntField(default=0)

    status = fields.IntField(default=0)
    lifetime = fields.IntField(default=0)

    storeMsgMetadata = fields.BooleanField(default=True)
    msgMetadataLifetime = fields.IntField(default=0)

    dateAdded = fields.DatetimeField(auto_now_add=True)
    dateActiveLast = fields.DatetimeField(auto_now_add=True)


class PubSubMsgRecord(Model):
    sizeRaw = fields.IntField(default=0)
    sizeTr = fields.IntField(default=0)
    seqNo = fields.BinaryField(null=True)
    senderPeerId = fields.CharField(max_length=128)

    dateRcv = fields.DatetimeField(auto_now_add=True)

    channel = fields.ForeignKeyField(
        'models.PubSubChannel',
        related_name='channel',
        through='messagerecord_channel',
        description='PS Channel')


class PubSubMsgAttrRecord(Model):
    msgType = fields.CharField(max_length=64)

    attrName = fields.CharField(max_length=64)
    attrStrValue = fields.CharField(max_length=512)

    date = fields.DatetimeField(auto_now_add=True)
    expires = fields.DatetimeField(null=True)

    msgrecord = fields.ForeignKeyField(
        'models.PubSubMsgRecord',
        related_name='msgrecord',
        through='attrrecord_msg',
        description='Message record')
