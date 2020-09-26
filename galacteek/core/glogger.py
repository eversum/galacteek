import sys

from logbook import Logger, StreamHandler
from logbook.more import ColorizedStderrHandler
from logbook.helpers import u
from logbook.compat import redirect_warnings
from logbook.compat import redirect_logging

mainFormatString = u(
    '[{record.time:%Y-%m-%d %H:%M:%S.%f%z}] '
    '{record.level_name}: {record.module}: {record.message}')

easyFormatString = u(
    '[{record.time: %H:%M:%S}] '
    '{record.module}: {record.message}')


class ColorizedHandler(ColorizedStderrHandler):
    dark_colors = ["black", "darkred", "darkgreen", "brown", "darkblue",
                   "purple", "teal", "lightgray"]
    light_colors = ["darkgray", "red", "green", "yellow", "blue",
                    "fuchsia", "turquoise", "white"]

    def get_color(self, record):
        if not record.module:
            return 'lightgray'
        elif record.module == 'galacteek.core.asynclib':
            return 'darkred'
        elif record.module.startswith('galacteek.core'):
            return 'red'
        elif record.module.startswith('galacteek.crypto'):
            return 'green'
        elif record.module.startswith('galacteek.ipfs'):
            return 'turquoise'
        elif record.module.startswith('galacteek.did'):
            return 'turquoise'
        elif record.module.startswith('galacteek.dweb.page'):
            return 'brown'
        elif record.module == 'galacteek.user':
            return 'fuchsia'
        elif record.module == 'galacteek.hashmarks':
            return 'brown'
        elif record.module == 'galacteek.application':
            return 'blue'
        elif record.module.startswith('galacteek.ui'):
            return 'yellow'
        else:
            return 'lightgray'


def basicConfig(level='INFO', redirectLogging=False, colorized=False):
    if not colorized:
        handler = StreamHandler(sys.stderr, level=level, bubble=True)
    else:
        handler = ColorizedHandler(level=level, bubble=True)
        handler.force_color()

    handler.format_string = mainFormatString
    handler.push_application()

    if redirectLogging:
        redirect_logging()
        redirect_warnings()


loggerMain = Logger('galacteek')
loggerUser = Logger('galacteek.user')
