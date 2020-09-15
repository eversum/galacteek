
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
                        "type": "string"
                    },
                },
                "required": [
                    "megadagcid",
                    "dagcid",
                    "dagclass",
                    "dagname",
                    "daguid"
                ]
            }
        },
        "required": ["msgtype", "exchange"]
    }

    @staticmethod
    def make(dagClass: str, dagCid: str, mDagCid: str,
             name: str, dagUid: str):
        msg = DAGExchangeMessage({
            'msgtype': DAGExchangeMessage.TYPE,
            'exchange': {
                'dagcid': dagCid,
                'megadagcid': mDagCid,
                'dagclass': dagClass,
                'dagname': name,
                'daguid': dagUid
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
    def dagUid(self):
        return self.jsonAttr('exchange.daguid')

    @property
    def dagName(self):
        return self.jsonAttr('exchange.dagname')
