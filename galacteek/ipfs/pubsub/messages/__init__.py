import re
import json
import collections

from jsonschema import validate
from jsonschema.exceptions import ValidationError

from galacteek import log
from galacteek.ipfs import ipfsOp
from galacteek.core.jtraverse import traverseParser


class Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, PubsubMessage):
            return obj.data
        return json.JSONEncoder.default(self, obj)


class PubsubMessage(collections.UserDict):
    uidRe = re.compile(
        r'[a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12}')

    def __init__(self, *args, **kw):
        super(PubsubMessage, self).__init__(*args, **kw)
        self.schema = None

    def __str__(self):
        return json.dumps(self.data)

    def pretty(self):
        return json.dumps(self.data, indent=4)

    @property
    def parser(self):
        return traverseParser(self.data)

    def validSchema(self, schema=None):
        sch = schema if schema else self.__class__.schema

        try:
            validate(self.data, sch)
        except ValidationError as verr:
            log.debug('Invalid JSON schema error: {}'.format(str(verr)))
            return False
        else:
            return True

    def jsonAttr(self, path):
        return self.parser.traverse(path)

    def valid(self):
        return self.validSchema()

    @staticmethod
    def make(*args, **kw):
        raise Exception('Implement static method make')

    @property
    def msgType(self):
        # msgtype should be in all JSON messages
        return self.jsonAttr('msgtype')


class LDMessage(PubsubMessage):
    @ipfsOp
    async def expanded(self, ipfsop):
        try:
            async with ipfsop.ldOps() as ld:
                return await ld.expandDocument(self.data)
        except Exception as err:
            print(str(err))

    async def expandedDump(self):
        print(json.dumps(await self.expanded(), indent=4))
