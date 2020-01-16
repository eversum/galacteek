import uuid
import socket
from datetime import datetime
from datetime import timezone
from dateutil import parser as duparser
from sys import version_info
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from contextlib import closing


from PyQt5.QtWidgets import QApplication


def runningApp():
    return QApplication.instance()


def utcDatetime():
    return datetime.now(timezone.utc)


def utcDatetimeIso():
    return utcDatetime().isoformat()


def datetimeIsoH():
    return datetime.now().isoformat(sep=' ')


def parseDate(date):
    if isinstance(date, str):
        try:
            return duparser.parse(date)
        except Exception:
            pass


def isoformat(dt, sep=' ', timespec='seconds'):
    if version_info.major == 3 and version_info.minor < 6:
        return dt.isoformat(sep)
    elif version_info.major == 3 and version_info.minor >= 6:
        return dt.isoformat(sep, timespec=timespec)


def nonce():
    return str(uuid.uuid4())


def jsonSchemaValidate(data, schema):
    try:
        validate(data, schema)
    except ValidationError:
        return False
    else:
        return True


def unusedTcpPort():
    try:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.bind(('', 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return s.getsockname()[1]
    except Exception:
        return None
