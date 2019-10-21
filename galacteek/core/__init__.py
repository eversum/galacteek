from datetime import datetime
from datetime import timezone
from dateutil import parser as duparser
from sys import version_info

from PyQt5.QtWidgets import QApplication


def runningApp():
    return QApplication.instance()


def utcDatetime():
    return datetime.now(timezone.utc)


def utcDatetimeIso():
    return utcDatetime().isoformat()


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
