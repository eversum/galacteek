import os.path

from html.parser import HTMLParser

import aioipfs


class TitleParser(HTMLParser):
    def __init__(self):
        super().__init__()

        self.inHead = False
        self.inTitle = False
        self.data = ''
        self.title = None

    def handle_starttag(self, tag, attrs):
        self.data = ''
        if tag == 'head':
            self.inHead = True
        if tag == 'title' and self.inHead is True:
            self.inTitle = True

    def handle_endtag(self, tag):
        if tag == 'head':
            self.inHead = False
        if tag == 'title' and self.inHead is True:
            self.inTitle = False
            self.title = self.data

    def handle_data(self, data):
        self.data += data

    def getTitle(self):
        if self.title:
            return self.title.strip()


def runTitleParser(data):
    try:
        parser = TitleParser()
        parser.feed(data.decode())
        return parser.getTitle()
    except BaseException:
        return None


async def getTitleDirectory(client, path):
    indexPath = os.path.join(path, 'index.html')

    try:
        data = await client.cat(indexPath)
    except aioipfs.APIError as exc:
        if exc.code == 0 and exc.message.startswith('no link named'):
            return None
        if exc.code == 0 and exc.message == 'this dag node is a directory':
            # Wicked!
            return None
    else:
        return runTitleParser(data)


async def getTitle(client, path):
    """
    Lookup IPFS object with path and if it's an HTML document, return its title
    If path is a directory, call getTitleDirectory() which will return the
    title of the index.html file inside that directory if found
    """
    try:
        data = await client.cat(path)
    except aioipfs.APIError as exc:
        if exc.code == 0 and exc.message.startswith('no link named'):
            return None
        if exc.code == 0 and exc.message == 'this dag node is a directory':
            return await getTitleDirectory(client, path)
    else:
        return runTitleParser(data)
