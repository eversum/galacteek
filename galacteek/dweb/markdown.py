import markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import Pattern
import xml.etree.ElementTree as etree

from galacteek.dweb.pygmentedmarkdown import CodeBlockExtension

from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import ipfsCid32Re
from galacteek.ipfs.cidhelpers import ipfsCidRe
from galacteek.ipfs.cidhelpers import ipfsPathMagicRe
from galacteek.ipfs.cidhelpers import ipnsPathMagicRe
from galacteek.ipfs.cidhelpers import ipfsMdMagic


class LinkBuilder:
    def mkLink(self, a, label, title, href, parent=None):
        if parent is not None:
            el = etree.SubElement(parent, 'a')
        else:
            el = etree.Element('a')

        if '!' in a:
            img = etree.SubElement(el, 'img')

            img.set('src', href)
            img.set('width', '150px')
            img.set('height', 'auto')
            img.set('title', label)
        elif '%' in a:
            vid = etree.SubElement(el, 'video')

            vid.set('src', href)
            vid.set('controls', '')
            vid.set('crossorigin', 'anonymous')
            return vid
        else:
            el.text = label
            el.set('title', title)

        el.set('href', href)

        return el

    def mkAllLinks(self, a, label, ipfsPath):
        ac = a.count('@')
        root = etree.Element('ul')

        l1 = etree.SubElement(root, 'li')
        l2 = etree.SubElement(root, 'li')

        self.mkLink(a, f'(i) {label}', label, ipfsPath.ipfsUrl, parent=l1)
        self.mkLink(a, f'(gw) {label}', label, ipfsPath.publicGwUrl, parent=l2)

        if ac > 2:
            l3 = etree.SubElement(root, 'li')
            self.mkLink(a, f'(dw) {label}', label, ipfsPath.dwebUrl, parent=l3)

        return root

    def link(self, m, ipfsPath):
        if ipfsPath.valid:
            linkName = m.group('linkname')
            a = m.group('a')
            ac = a.count('@')

            if ac >= 2:
                return self.mkAllLinks(
                    a,
                    linkName if linkName else ipfsPath.objPath,
                    ipfsPath
                )
            else:
                if '%' in a:
                    url = ipfsPath.dwebUrl
                else:
                    url = ipfsPath.ipfsUrl

                return self.mkLink(
                    a,
                    linkName if linkName else ipfsPath.objPath,
                    ipfsPath.objPath, url)


class IPFSPathPattern(Pattern, LinkBuilder):
    def __init__(self, config, md):
        super(IPFSPathPattern, self).__init__(ipfsPathMagicRe.pattern, md)
        self.config = config

    def handleMatch(self, m):
        fp = m.group('fullpath')
        return self.link(m, IPFSPath(fp, autoCidConv=True))


class IPNSPathPattern(Pattern, LinkBuilder):
    def __init__(self, config, md):
        super(IPNSPathPattern, self).__init__(ipnsPathMagicRe.pattern, md)
        self.config = config

    def handleMatch(self, m):
        fp = m.group('fullpath')
        return self.link(m, IPFSPath(fp, autoCidConv=True))


class IPFSCID32Pattern(Pattern, LinkBuilder):
    def __init__(self, config, md):
        RE = ipfsMdMagic + ipfsCid32Re.pattern

        super(IPFSCID32Pattern, self).__init__(RE, md)
        self.config = config

    def handleMatch(self, m):
        return self.link(m, IPFSPath(m.group('cid'), autoCidConv=True))


class IPFSCIDPattern(Pattern, LinkBuilder):
    def __init__(self, config, md):
        RE = ipfsMdMagic + ipfsCidRe.pattern

        super(IPFSCIDPattern, self).__init__(RE, md)
        self.config = config

    def handleMatch(self, m):
        return self.link(m, IPFSPath(m.group('cid'), autoCidConv=True))


class IPFSLinksExtension(Extension):
    def __init__(self, *args, **kwargs):
        super(IPFSLinksExtension, self).__init__(*args, **kwargs)

    def extendMarkdown(self, md, md_globals):
        md.ESCAPED_CHARS.append('@')
        md.inlinePatterns['ipfslink'] = IPFSPathPattern(self.getConfigs(), md)
        md.inlinePatterns['ipfscid32'] = IPFSCID32Pattern(
            self.getConfigs(), md)
        md.inlinePatterns['ipfscid'] = IPFSCIDPattern(
            self.getConfigs(), md)
        md.inlinePatterns['ipnspath'] = IPNSPathPattern(self.getConfigs(), md)


def markitdown(text):
    return markdown.markdown(
        text, extensions=[
            CodeBlockExtension(),
            IPFSLinksExtension(),
            'attr_list',
            'mdx_unimoji'
        ]
    )
