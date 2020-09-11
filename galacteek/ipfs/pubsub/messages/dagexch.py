from galacteek.ipfs.pubsub.messages import PubsubMessage
from galacteek.ipfs.cidhelpers import ipfsCid32Re


class DAGExchangeMessage(PubsubMessage):
    TYPE = 'DAGExchangeMessage'

    schema = {
        "type": "object",
        "properties": {
            "msgtype": {"type": "string"},
            "exchange": {
                "type": "object",
                "properties": {
                    "megadagcid": {
                        "type": "string",
                        "pattern": ipfsCid32Re.pattern
                    },
                    "dagcid": {
                        "type": "string",
                        "pattern": ipfsCid32Re.pattern
                    },
                    "dagclass": {
                        "type": "string"
                    },
                    "dagname": {
                        "type": "string"
                    },
                    "daguid": {
                        "type": "string",
                        "pattern": r"[a-f0-9\-]{36,72}"
                    },
                    "servicetoken": {
                        "type": "string",
                        "pattern": r"[a-f0-9]{64,128}"
                    },
                    "signerpubkeycid": {
                        "type": "string",
                        "pattern": ipfsCid32Re.pattern
                    },
                },
                "required": [
                    "servicetoken",
                    "megadagcid",
                    "dagcid",
                    "dagclass",
                    "dagname",
                    "daguid",
                    "signerpubkeycid"
                ]
            }
        },
        "required": ["msgtype", "exchange"]
    }

    @staticmethod
    def make(dagClass: str, dagCid: str, mDagCid: str,
             name: str, dagUid: str, signerPubKeyCid: str,
             serviceToken: str):
        msg = DAGExchangeMessage({
            'msgtype': DAGExchangeMessage.TYPE,
            'exchange': {
                'dagcid': dagCid,
                'megadagcid': mDagCid,
                'dagclass': dagClass,
                'dagname': name,
                'daguid': dagUid,
                'signerpubkeycid': signerPubKeyCid,
                'servicetoken': serviceToken
            }
        })
        return msg

    @property
    def dagClass(self):
        return self.jsonAttr('exchange.dagclass')

    @property
    def dagCid(self):
        return self.jsonAttr('exchange.dagcid')

    @property
    def megaDagCid(self):
        return self.jsonAttr('exchange.megadagcid')

    @property
    def dagUid(self):
        return self.jsonAttr('exchange.daguid')

    @property
    def dagName(self):
        return self.jsonAttr('exchange.dagname')

    @property
    def signerPubKeyCid(self):
        return self.jsonAttr('exchange.signerpubkeycid')

    @property
    def serviceToken(self):
        return self.jsonAttr('exchange.servicetoken')
