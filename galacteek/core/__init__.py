from sys import version_info

from PyQt5.QtWidgets import QApplication


def runningApp():
    return QApplication.instance()


def isoformat(dt, sep=' ', timespec='seconds'):
    if version_info.major == 3 and version_info.minor < 6:
        return dt.isoformat(sep)
    elif version_info.major == 3 and version_info.minor >= 6:
        return dt.isoformat(sep, timespec=timespec)
