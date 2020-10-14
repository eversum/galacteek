from datetime import datetime
from datetime import timedelta

from galacteek.database.models.pubsub import *


class PSTopicManager:
    def __init__(self, channel):
        self.channel = channel

    async def active(self):
        self.channel.dateActiveLast = datetime.now()
        await self.channel.save()

    async def recordMessage(self, sender, size, **kw):
        rec = PubSubMsgRecord(channel=self.channel, sizeRaw=size,
                              senderPeerId=sender, **kw)
        await rec.save()

        await self.active()
        return rec

    async def recordMsgAttribute(self, msgrecord, msgType, attrName, value):
        try:
            rec = PubSubMsgAttrRecord(msgrecord=msgrecord, attrName=attrName,
                                      msgType=msgType,
                                      attrStrValue=str(value))
            await rec.save()
            return rec
        except Exception:
            pass

    async def searchMsgAttribute(self, msgType, attrName, value, dateMin=None):
        dateMin = dateMin if dateMin else datetime.now() - timedelta(days=1)

        return await PubSubMsgAttrRecord.filter(
            msgrecord__channel__id=self.channel.id,
            date__gt=dateMin,
            msgType=msgType,
            attrName=attrName,
            attrStrValue=value).all()


async def psManagerForTopic(topic, encType=0):
    chan = await PubSubChannel.filter(topic=topic).first()
    if not chan:
        chan = PubSubChannel(topic=topic, encType=encType)
        await chan.save()

    return PSTopicManager(chan)
