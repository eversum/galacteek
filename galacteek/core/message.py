import json
import collections
import re

from galacteek.core.jtraverse import traverseParser
from galacteek.core import jsonSchemaValidate


class Message(collections.UserDict):
    uidRe = re.compile(
        r'[a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12}')

    def __init__(self, *args, **kw):
        super(Message, self).__init__(*args, **kw)
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
        return jsonSchemaValidate(self.data, sch)

    def jsonAttr(self, path):
        return self.parser.traverse(path)

    def valid(self):
        return self.validSchema()

    @staticmethod
    def make(*args, **kw):
        raise Exception('Implement static method make')
