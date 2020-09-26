from PyQt5.QtCore import QUrl

from galacteek.ipfs import ipfsOpFn
from galacteek.dweb.page import DWebView
from galacteek.dweb.page import IPFSPage
from galacteek.dweb.webscripts import scriptFromQFile


class QuestServicePage(IPFSPage):
    pass


@ipfsOpFn
async def loadQuestService(ipfsop, parent=None):
    wsAddrs = await ipfsop.nodeWsAdresses()

    page = QuestServicePage(
        'quest.html',
        url=QUrl('file:/quest'))

    rxscript = scriptFromQFile(
        'rxjs',
        ':/share/js/rxjs.umd.min.js'
    )

    script = scriptFromQFile(
        'quest',
        ':/share/js/quest/quest-service.js'
    )

    pScript = scriptFromQFile(
        'quest-extension',
        ':/share/js/quest/quest-service-ext.js'
    )

    try:
        # Pass the ws bootstrap addr
        wsAddr = wsAddrs.pop()
        code = pScript.sourceCode().replace(
            "@@WS_BOOTSTRAP_ADDR@@",
            wsAddr
        )
        pScript.setSourceCode(code)
    except Exception as e:
        raise e
        return None, None

    page.webScripts.insert(rxscript)
    page.webScripts.insert(script)
    page.webScripts.insert(pScript)

    view = DWebView(page=page)

    return view, page
