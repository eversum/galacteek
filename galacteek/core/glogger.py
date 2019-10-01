import sys

from logbook import Logger, StreamHandler
from logbook.helpers import u
from logbook.compat import redirect_warnings
from logbook.compat import redirect_logging

mainFormatString = u(
    '[{record.time:%Y-%m-%d %H:%M:%S.%f%z}] '
    '{record.level_name}: {record.module}: {record.message}')

easyFormatString = u(
    '[{record.time: %H:%M:%S}] '
    '{record.module}: {record.message}')


def basicConfig(level='INFO', redirectLogging=False):
    handler = StreamHandler(sys.stderr, level=level, bubble=True)
    handler.format_string = mainFormatString
    handler.push_application()

    if redirectLogging:
        redirect_logging()
        redirect_warnings()


loggerMain = Logger('galacteek')
loggerUser = Logger('galacteek.user')
