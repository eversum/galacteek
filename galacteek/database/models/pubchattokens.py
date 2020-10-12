from tortoise.models import Model
from tortoise import fields


class PubChatSessionToken(Model):
    # id = fields.IntField(pk=True)

    cid = fields.CharField(max_length=128, unique=True, pk=True)
    channel = fields.CharField(max_length=128)
    secTopic = fields.CharField(max_length=256)
    peerId = fields.CharField(max_length=128)

    did = fields.CharField(max_length=256, null=True)
    cpass = fields.CharField(max_length=128, null=True)
    pubKeyCid = fields.CharField(max_length=128, null=True)
    encType = fields.CharField(max_length=32, null=True)

    ltLast = fields.IntField(default=0)
    status = fields.IntField(default=0)
    lifetime = fields.IntField(default=0)

    dateAdded = fields.DatetimeField(auto_now_add=True)
