from galacteek.ipfs.pubsub.messages import PubsubMessage
from galacteek.ipfs.cidhelpers import ipfsCid32Re
from galacteek.core import utcDatetimeIso


class DAGExchangeMessage(PubsubMessage):
    TYPE = 'DAGExchangeMessage'

    VALID_TYPES = [
        TYPE,
        'DAGExchangeMessageV1'
    ]

    schema = {
        "type": "object",
        "properties": {
            "msgtype": {"type": "string"},
            "version": {"type": "integer"},
            "date": {"type": "string"},
            "rev": {"type": "string"},
            "exchange": {
                "type": "object",
                "properties": {
                    "megaDagCid": {
                        "type": "string",
                        "pattern": ipfsCid32Re.pattern
                    },
                    "dagCid": {
                        "type": "string",
                        "pattern": ipfsCid32Re.pattern
                    },
                    "dagClass": {
                        "type": "string",
                        "pattern": r"\w{2,32}"
                    },
                    "dagNet": {
                        "type": "string",
                        "pattern": r"\w{2,32}"
                    },
                    "dagName": {
                        "type": "string",
                        "pattern": r"\w{2,32}"
                    },
                    "dagUid": {
                        "type": "string",
                        "pattern": r"[a-f0-9\-]{36,72}"
                    },
                    "signerPubKeyCid": {
                        "type": "string",
                        "pattern": ipfsCid32Re.pattern
                    },
                    "session": {
                        "type": "object",
                        "properties": {
                            "serviceToken": {
                                "type": "string",
                                "pattern": r"[a-f0-9]{64,128}"
                            },
                            "snakeOil": {
                                "type": "string",
                                "pattern": r"[a-f0-9]{128}"
                            }
                        },
                        "required": [
                            "serviceToken",
                            "snakeOil"
                        ]
                    }
                },
                "required": [
                    "megaDagCid",
                    "dagCid",
                    "dagClass",
                    "dagNet",
                    "dagUid",
                    "signerPubKeyCid",
                    "session"
                ]
            }
        },
        "required": ["msgtype", "exchange"]
    }

    @staticmethod
    def make(revision: str,
             dagClass: str, dagCid: str,
             dagNet: str, dagName: str,
             dagUid: str,
             signerPubKeyCid: str,
             mDagCid: str,
             serviceToken: str,
             snakeOil: str):
        return DAGExchangeMessage({
            'msgtype': DAGExchangeMessage.TYPE,
            'version': 2,
            'date': utcDatetimeIso(),
            'rev': revision,
            'exchange': {
                'dagCid': dagCid,
                'megaDagCid': mDagCid,
                'dagClass': dagClass,
                'dagNet': dagNet,
                'dagName': dagName,
                'dagUid': dagUid,
                'signerPubKeyCid': signerPubKeyCid,
                'session': {
                    'serviceToken': serviceToken,
                    'snakeOil': snakeOil
                }
            }
        })

    @property
    def revision(self):
        return self.jsonAttr('rev')

    @property
    def dagClass(self):
        return self.jsonAttr('exchange.dagClass')

    @property
    def dagCid(self):
        return self.jsonAttr('exchange.dagCid')

    @property
    def megaDagCid(self):
        return self.jsonAttr('exchange.megaDagCid')

    @property
    def dagUid(self):
        return self.jsonAttr('exchange.dagUid')

    @property
    def dagName(self):
        return self.jsonAttr('exchange.dagName')

    @property
    def dagNet(self):
        return self.jsonAttr('exchange.dagNet')

    @property
    def signerPubKeyCid(self):
        return self.jsonAttr('exchange.signerPubKeyCid')

    @property
    def serviceToken(self):
        return self.jsonAttr('exchange.session.serviceToken')

    @property
    def snakeOil(self):
        return self.jsonAttr('exchange.session.snakeOil')
