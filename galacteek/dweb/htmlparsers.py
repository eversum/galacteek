from html.parser import HTMLParser
from urllib.parse import unquote

from PyQt5.QtCore import QUrl

from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.core.schemes import isIpfsUrl


class IPFSLinksParser(HTMLParser):
    """
    Primitive HTML IPFS links parser, used to scan IPFS URLs in
    HTML pages rendered by the browser
    """
    def __init__(self, basePath):
        """
        :param IPFSPath basePath: The page's base IPFS path
        """

        super().__init__()
        self.links = []
        self.base = basePath

    def handle_starttag(self, tag, alist):
        if tag != 'a':
            return

        attrs = dict(alist)
        href = attrs.get('href')

        if not isinstance(href, str):
            return

        if len(href) > 1024:
            return

        href = unquote(href)

        url = QUrl(href)
        if not url.isValid():
            return

        if not url.scheme() or url.isRelative():
            # Relative URL
            p = self.base.child(href)
            if p and self.pathValid(p):
                self.links.append(p)

        elif isIpfsUrl(url):
            # Absolute URL
            p = IPFSPath(url.toString())
            if self.pathValid(p):
                self.links.append(p)

    def pathValid(self, p):
        return p.valid and p != self.base

    def handle_endtag(self, tag):
        pass

    def handle_data(self, data):
        pass
