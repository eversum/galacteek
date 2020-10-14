from galacteek.core import utcDatetimeIso
from galacteek.core.iphandle import ipHandleRe
from galacteek.ipfs.cidhelpers import ipfsCid32Re
from galacteek.ipfs.cidhelpers import stripIpfs
from galacteek.ipfs.pubsub.messages import PubsubMessage
from galacteek.did import ipidIdentRe


class MarksBroadcastMessage(PubsubMessage):
    TYPE = 'hashmarks.broadcast'

    schema = {
        "title": "Hashmarks broadcast",
        "description": "Hashmarks broadcast message",
        "type": "object",
        "properties": {
            "msgtype": {"type": "string"},
            "msg": {
                "type": "object",
                "properties": {
                    "peerid": {"type": "string"},
                    "ipfsmarks": {
                        "type": "object",
                        "properties": {
                            "categories": {"type": "object"}
                        }
                    }
                },
                "required": ["peerid", "ipfsmarks"]
            },
        },
        "required": ["msgtype", "msg"]
    }

    @staticmethod
    def make(peerid, ipfsmarks):
        msg = MarksBroadcastMessage({
            'msgtype': MarksBroadcastMessage.TYPE,
            'date': utcDatetimeIso(),
            'msg': {
                'peerid': peerid,
                'ipfsmarks': ipfsmarks
            }
        })
        return msg

    @property
    def peer(self):
        return self.jsonAttr('msg.peerid')

    @property
    def marks(self):
        return self.jsonAttr('msg.ipfsmarks')


class PeerIdentMessageV3(PubsubMessage):
    TYPE = 'peerident.v3'

    schema = {
        "title": "Peer ident",
        "description": "Peer identification message, V3",
        "type": "object",
        "properties": {
            "msgtype": {
                "type": "string",
                "pattern": "^{0}$".format(TYPE)
            },
            "msg": {
                "type": "object",
                "properties": {
                    "peerid": {"type": "string"},
                    "user": {
                        "type": "object",
                        "properties": {
                            "identity": {
                                "type": "object",
                                "properties": {
                                    "vplanet": {
                                        "type": "string"
                                    },
                                    "iphandle": {
                                        "type": "string",
                                        "pattern": ipHandleRe.pattern
                                    },
                                    "persondid": {
                                        "type": "string",
                                        "pattern": ipidIdentRe.pattern
                                    },
                                    "iphandleqrpngcid": {
                                        "type": "string",
                                        "pattern": ipfsCid32Re.pattern
                                    },
                                    "orgs": {
                                        "type": "array",
                                        "items": {
                                            "type": "string",
                                            "pattern": ipidIdentRe.pattern
                                        }
                                    }
                                },
                                "required": [
                                    "vplanet",
                                    "iphandle",
                                    "iphandleqrpngcid",
                                    "persondid"
                                ]
                            }
                        },
                        "required": [
                            "identity"
                        ],
                    }
                },
                "required": ["peerid"]
            },
        },
        "required": ["msgtype", "msg"]
    }

    @staticmethod
    async def make(peerId, userDagCid, userDagIpns, userInfo,
                   personDid, personDidCurCid,
                   p2pServices=None):
        p2pServices = p2pServices if p2pServices else []
        qrPngNodeCid = stripIpfs(
            await userInfo.identityResolve('iphandleqr/png')
        )

        msg = PeerIdentMessageV3({
            'msgtype': PeerIdentMessageV3.TYPE,
            'date': utcDatetimeIso(),
            'msg': {
                'peerid': peerId,
                'user': {
                    'identity': {
                        'vplanet': userInfo.vplanet,
                        'iphandle': userInfo.iphandle,
                        'iphandleqrpngcid': qrPngNodeCid,
                        'persondid': userInfo.personDid,
                        'persondidcurrentcid': personDidCurCid,
                        'orgs': []
                    },
                    'p2pservices': p2pServices
                }
            }
        })
        return msg

    @property
    def peer(self):
        return self.jsonAttr('msg.peerid')

    @property
    def iphandle(self):
        return self.jsonAttr('msg.user.identity.iphandle')

    @property
    def iphandleqrpngcid(self):
        return self.jsonAttr('msg.user.identity.iphandleqrpngcid')

    @property
    def vplanet(self):
        return self.jsonAttr('msg.user.identity.vplanet')

    @property
    def personDid(self):
        return self.jsonAttr('msg.user.identity.persondid')

    @property
    def personDidCurCid(self):
        return self.jsonAttr('msg.user.identity.persondidcurrentcid')

    def dateMessage(self):
        return self.jsonAttr('date')

    @property
    def msgdata(self):
        return self.data['msg']

    def valid(self):
        return self.validSchema(schema=PeerIdentMessageV3.schema)


class PeerIdentMessageV4(PubsubMessage):
    TYPE = 'peerident'

    VALID_TYPES = [
        'peerident',
        'peerident.v4'
    ]

    schema = {
        "title": "Peer ident",
        "description": "Peer identification message, V4",
        "type": "object",
        "properties": {
            "msgtype": {
                "type": "string",
                "pattern": "^{0}".format(TYPE)
            },
            "version": {"type": "integer"},
            "msg": {
                "type": "object",
                "properties": {
                    "peerid": {"type": "string"},
                    "identToken": {
                        "type": "string",
                        "pattern": r"[a-f0-9]{128}"
                    },
                    "software": {
                        "type": "object",
                        "properties": {
                            "galacteekVersion": {
                                "type": "string"
                            }
                        }
                    },
                    "user": {
                        "type": "object",
                        "properties": {
                            "crypto": {
                                "type": "object",
                                "properties": {
                                    "rsaDefPubKeyCid": {
                                        "type": "string",
                                        "pattern": ipfsCid32Re.pattern
                                    },
                                    "pssCurDidSigCid": {
                                        "type": "string",
                                        "pattern": ipfsCid32Re.pattern
                                    }
                                },
                                "required": [
                                    "rsaDefPubKeyCid",
                                    "pssCurDidSigCid"
                                ]
                            },
                            "edags": {
                                "type": "object",
                                "properties": {
                                    "peersGraph": {
                                        "type": "object",
                                        "properties": {
                                            "cid": {
                                                "type": "string",
                                                "pattern": ipfsCid32Re.pattern
                                            }
                                        }
                                    }
                                },
                                "required": ["peersGraph"]
                            },
                            "identity": {
                                "type": "object",
                                "properties": {
                                    "vplanet": {
                                        "type": "string"
                                    },
                                    "ipHandle": {
                                        "type": "string",
                                        "pattern": ipHandleRe.pattern
                                    },
                                    "personDid": {
                                        "type": "string",
                                        "pattern": ipidIdentRe.pattern
                                    },
                                    "ipHandleQrPngCid": {
                                        "type": "string",
                                        "pattern": ipfsCid32Re.pattern
                                    },
                                    "orgs": {
                                        "type": "array",
                                        "items": {
                                            "type": "string",
                                            "pattern": ipidIdentRe.pattern
                                        }
                                    }
                                },
                                "required": [
                                    "vplanet",
                                    "ipHandle",
                                    "ipHandleQrPngCid",
                                    "personDid"
                                ]
                            }
                        },
                        "required": [
                            "identity",
                            "crypto",
                            "edags"
                        ],
                    }
                },
                "required": ["peerid", "identToken"]
            },
        },
        "required": ["msgtype", "msg"]
    }

    @staticmethod
    async def make(peerId: str,
                   identToken: str,
                   userDagCid: str,
                   userDagIpns: str,
                   userInfo,
                   personDid: str,
                   personDidCurCid: str,
                   rsaDefPubKeyCid: str,
                   pssSigCurDid: str,
                   edagNetworkCid: str,
                   p2pServices=None):
        from galacteek import __version__ as gversion

        p2pServices = p2pServices if p2pServices else []
        qrPngNodeCid = stripIpfs(
            await userInfo.identityResolve('iphandleqr/png')
        )

        return PeerIdentMessageV4({
            'msgtype': PeerIdentMessageV4.TYPE,
            'date': utcDatetimeIso(),
            'version': 4,
            'msg': {
                'peerid': peerId,
                'identToken': identToken,
                'software': {
                    'galacteekVersion': gversion
                },
                'user': {
                    'identity': {
                        'vplanet': userInfo.vplanet,
                        'ipHandle': userInfo.iphandle,
                        'ipHandleQrPngCid': qrPngNodeCid,
                        'personDid': userInfo.personDid,
                        'personDidCurrentCid': personDidCurCid,
                        'orgs': []
                    },
                    'crypto': {
                        'rsaDefPubKeyCid': rsaDefPubKeyCid,
                        'pssCurDidSigCid': pssSigCurDid
                    },
                    'edags': {
                        'peersGraph': {
                            'cid': edagNetworkCid
                        }
                    },
                    'p2pservices': p2pServices
                }
            }
        })

    @property
    def peer(self):
        return self.jsonAttr('msg.peerid')

    @property
    def identToken(self):
        return self.jsonAttr('msg.identToken')

    @property
    def iphandle(self):
        return self.jsonAttr('msg.user.identity.ipHandle')

    @property
    def iphandleqrpngcid(self):
        return self.jsonAttr('msg.user.identity.ipHandleQrPngCid')

    @property
    def vplanet(self):
        return self.jsonAttr('msg.user.identity.vplanet')

    @property
    def personDid(self):
        return self.jsonAttr('msg.user.identity.personDid')

    @property
    def personDidCurCid(self):
        return self.jsonAttr('msg.user.identity.personDidCurrentCid')

    @property
    def defaultRsaPubKeyCid(self):
        return self.jsonAttr('msg.user.crypto.rsaDefPubKeyCid')

    @property
    def pssSigCurDid(self):
        return self.jsonAttr('msg.user.crypto.pssCurDidSigCid')

    @property
    def edagCidNetwork(self):
        return self.jsonAttr('msg.user.edags.peersGraph.cid')

    def dateMessage(self):
        return self.jsonAttr('date')

    @property
    def msgdata(self):
        return self.data['msg']

    def valid(self):
        return self.validSchema(schema=PeerIdentMessageV4.schema)


class PeerIpHandleChosen(PubsubMessage):
    TYPE = 'peeriphandlechange'

    schema = {
        "title": "Peer IP name",
        "description": "Peer IP name",
        "type": "object",
        "properties": {
            "msgtype": {
                "type": "string",
                "pattern": "^{0}$".format(TYPE)
            },
            "msg": {
                "type": "object",
                "properties": {
                    "peerid": {"type": "string"},
                    "iphandle": {
                        "type": "string",
                        "pattern": ipHandleRe.pattern
                    },
                    "iphandleqrpngcid": {"type": "string"}
                },
                "required": [
                    "iphandle",
                    "iphandleqrpngcid"
                ]
            }
        },
        "required": ["msgtype", "msg"]
    }

    @staticmethod
    def make(peerId, ipHandle: str,
             ipHandleQrCid: str,
             ipHandleQrPngCid: str):

        msg = PeerIpHandleChosen({
            'msgtype': PeerIpHandleChosen.TYPE,
            'date': utcDatetimeIso(),
            'msg': {
                'peerid': peerId,
                'iphandle': ipHandle,
                'iphandleqrrawcid': ipHandleQrCid,
                'iphandleqrpngcid': ipHandleQrPngCid
            }
        })
        return msg

    @property
    def peer(self):
        return self.jsonAttr('msg.peerid')

    @property
    def iphandle(self):
        return self.jsonAttr('msg.iphandle')


class PeerLogoutMessage(PubsubMessage):
    TYPE = 'peerlogout'

    schema = {
        "type": "object",
        "properties": {
            "msgtype": {"type": "string"},
            "msg": {
                "type": "object",
                "properties": {
                    "peerid": {"type": "string"},
                },
                "required": ["peerid"]
            },
        },
        "required": ["msgtype", "msg"]
    }

    @staticmethod
    def make(peerid):
        msg = PeerLogoutMessage({
            'msgtype': PeerLogoutMessage.TYPE,
            'msg': {
                'peerid': peerid,
            }
        })
        return msg

    @property
    def peer(self):
        return self.jsonAttr('msg.peerid')

    def valid(self):
        return self.validSchema(schema=PeerLogoutMessage.schema)
