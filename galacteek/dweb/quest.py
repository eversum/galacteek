from PyQt5.QtCore import QUrl

from galacteek.dweb.page import DWebView
from galacteek.dweb.page import IPFSPage
from galacteek.dweb.webscripts import scriptFromQFile


class QuestServicePage(IPFSPage):
    pass


async def loadQuestService(self):
    page = QuestServicePage(
        'quest.html',
        url=QUrl('file:/quest'))

    script = scriptFromQFile(
        'quest',
        ':/share/js/quest-service.js'
    )

    page.webScripts.insert(script)
    view = DWebView(page=page)

    return view, page
