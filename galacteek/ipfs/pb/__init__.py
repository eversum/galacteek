"""
Protobuf definitions for IPFS
"""

import base64


UNIXFS_DT_RAW = 0
UNIXFS_DT_DIRECTORY = 1
UNIXFS_DT_FILE = 2
UNIXFS_DT_METADATA = 3
UNIXFS_DT_SYMLINK = 4
UNIXFS_DT_HAMTSHARD = 5


unixfsDtNames = {
    UNIXFS_DT_DIRECTORY: 'directory',
    UNIXFS_DT_FILE: 'file',
    UNIXFS_DT_HAMTSHARD: 'hamtshard',
    UNIXFS_DT_METADATA: 'metadata',
    UNIXFS_DT_RAW: 'raw',
    UNIXFS_DT_SYMLINK: 'symlink'
}


def decodeUnixfsDagNode(data):
    """
    Import unixfs_pb2 from the function for now, it's rather heavy
    to import protobuf on startup
    """

    from . import unixfs_pb2
    from .protobuf_to_dict import protobuf_to_dict

    try:
        message = unixfs_pb2.Data()
        message.MergeFromString(
            base64.b64decode(data))
        obj = protobuf_to_dict(message)
    except Exception:
        return None

    return {
        'type': obj['Type'],
        'size': obj.get('filesize'),
        'blocksizes': obj.get('blocksizes'),
        'data': obj.get('Data')
    }
