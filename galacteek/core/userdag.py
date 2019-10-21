import os.path
import uuid
import pkg_resources
from datetime import datetime
from datetime import timezone

from feedgen.feed import FeedGenerator

from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal

from galacteek import log
from galacteek import logUser
from galacteek import ensure
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.stat import StatInfo
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import joinIpns
from galacteek.core.analyzer import ResourceAnalyzer
from galacteek.core import isoformat
from galacteek.dweb import render
from galacteek.dweb.atom import DWEB_ATOM_FEEDFN

from galacteek.ipfs.dag import EvolvingDAG


POST_NODEKEY = '_post'
CATEGORIES_NODEKEY = '_categories'
TAGS_NODEKEY = '_tags'
METADATA_NODEKEY = '_metadata'
BLOG_NODEKEY = 'blog'
PINREQS_NODEKEY = 'pinrequests'


class UserDAG(EvolvingDAG):
    def updateDagSchema(self, root):
        changed = False

        if BLOG_NODEKEY not in root:
            root[BLOG_NODEKEY] = {
                TAGS_NODEKEY: {}
            }
            changed = True

        if PINREQS_NODEKEY not in root:
            root[PINREQS_NODEKEY] = []
            changed = True

        if METADATA_NODEKEY not in root:
            root[METADATA_NODEKEY] = {
                'site_name': None,
                'site_description': None,
                'date_updated': None
            }
            changed = True

        return changed

    def initDag(self):
        return {
            'index.html': 'Blank',
            'media': {
                'images': {},
            }
        }

    async def siteMetadata(self):
        return await self.get(METADATA_NODEKEY)

    async def neverUpdated(self):
        metadata = await self.siteMetadata()
        return metadata['date_updated'] is None


class UserWebsite(QObject):
    """
    The website associated to the user.

    Later on this should become more generic to create all kinds of apps
    """

    websiteUpdated = pyqtSignal()

    def __init__(self, edag, profile, ipnsKeyId, jinjaEnv, parent=None):
        super().__init__(parent)

        self._profile = profile
        self._ipnsKeyId = ipnsKeyId
        self._edag = edag
        self._jinjaEnv = jinjaEnv

        self._atomFeedFn = DWEB_ATOM_FEEDFN

        self._rscAnalyzer = ResourceAnalyzer(None)
        self._updating = False

    @property
    def edag(self):
        return self._edag

    @property
    def profile(self):
        return self._profile

    @property
    def updating(self):
        return self._updating

    @property
    def ipnsKey(self):
        return self._ipnsKeyId

    @property
    def siteUrl(self):
        return self.sitePath.dwebUrl

    @property
    def sitePath(self):
        return IPFSPath(joinIpns(self.ipnsKey))

    @property
    def atomFeedPath(self):
        return self.sitePath.child(self._atomFeedFn)

    @property
    def rssFeedPath(self):
        return self.sitePath.child('rss.xml')

    @property
    def dagUser(self):
        return self.profile.dagUser

    @property
    def dagRoot(self):
        return self.profile.dagUser.root

    @property
    def dagRequests(self):
        return self.dagRoot['pinrequests']

    @property
    def dagBlog(self):
        return self.dagRoot['blog']

    def debug(self, msg):
        return self.profile.debug(msg)

    @ipfsOp
    async def blogEntries(self, op):
        return await self.edag.list(path='blog')

    @ipfsOp
    async def blogPost(self, ipfsop, title, msg, category=None, author=None):
        async with self.edag:
            username = self.profile.userInfo.username
            uid = str(uuid.uuid4())
            postName = title.strip().lower().replace(' ', '-')

            exEntries = await self.blogEntries()
            if postName in exEntries:
                postName += uid[0:8]
                return False

            now = datetime.now(timezone.utc)

            postObject = {
                'blogpost': {
                    'body': msg,
                    'title': title,
                    'uuid': uid,
                    'postname': postName,  # name of the post's DAG node
                    'tags': [],
                    'category': 'test',
                    'author': author if author else username,
                    'date_published': isoformat(now),
                    'date_modified': isoformat(now)
                }
            }

            # Create the DAG node for this post
            # Its view will be rendered later on

            self.dagBlog[postName] = {
                POST_NODEKEY: postObject
            }

        await ipfsop.sleep(2)
        await self.update()

        logUser.info('Your blog post is online')
        return True

    @ipfsOp
    async def makePinRequest(self, op, title, descr, objects,
                             priority=0, tags=None):
        async with self.profile.dagUser as dag:
            # objects needs to be a list of IPFS objects paths

            if not isinstance(objects, list):
                return False

            username = self.profile.userInfo.username
            uid = str(uuid.uuid4())
            now = datetime.now(timezone.utc)

            objsReq = []

            for obj in objects:
                path = IPFSPath(obj)
                if not path.valid:
                    continue

                try:
                    mType, stat = await self._rscAnalyzer(path)
                except:
                    continue

                statInfo = StatInfo(stat)
                if not statInfo.valid:
                    continue

                objsReq.append({
                    'path': path.objPath,
                    'totalsize': statInfo.totalSize,
                    'content_type': str(mType) if mType else None
                })

            pinRequest = {
                'pinrequest': {
                    'body': None,
                    'title': title,
                    'description': descr,
                    'objects': objsReq,
                    'uuid': uid,
                    'tags': tags if tags else [],
                    'author': username,
                    'priority': priority,
                    'date_published': isoformat(now),
                    'version': 1
                }
            }

            dag.dagRoot[PINREQS_NODEKEY].append(pinRequest)

        await self.update()
        return True

    @ipfsOp
    async def init(self, ipfsop):
        # Import the assets

        assetsPath = pkg_resources.resource_filename('galacteek.templates',
                                                     'usersite/assets')
        self.assetsEntry = await ipfsop.addPath(assetsPath, recursive=True)

        if self.profile.userInfo.avatarCid:
            self.edag.root['media']['images']['avatar'] = self.edag.mkLink(
                self.profile.userInfo.avatarCid)

        if self.profile.ctx.hasRsc('ipfs-cube-64'):
            self.edag.root['media']['images']['ipfs-cube.png'] = \
                self.edag.mkLink(self.profile.ctx.resources['ipfs-cube-64'])
        if self.profile.ctx.hasRsc('atom-feed'):
            self.edag.root['media']['images']['atom-feed.png'] = \
                self.edag.mkLink(self.profile.ctx.resources['atom-feed'])

        self.edag.root['about.html'] = await self.renderLink(
            'usersite/about.html')

    def createFeed(self):
        # Create the feed

        feed = FeedGenerator()
        feed.id(self.siteUrl)
        feed.title("{0}'s dweb space".format(
            self.profile.userInfo.username))
        feed.author({
            'name': self.profile.userInfo.username,
            'email': self.profile.userInfo.email
        })
        feed.link(href=self.atomFeedPath.dwebUrl, rel='self')
        feed.language('en')
        return feed

    @ipfsOp
    async def update(self, op):
        if self.dagRoot is None or self.updating is True:
            return

        now = datetime.now(timezone.utc)
        self._updating = True

        assetsChanged = False
        blogPosts = []

        feed = self.createFeed()

        async with self.profile.dagUser as dag:
            if self.assetsEntry:
                resolved = await dag.resolve('assets')
                if resolved and self.assetsEntry.get('Hash') != resolved:
                    # The assets were modified (will need to fully regen)
                    assetsChanged = True

                dag.root['assets'] = dag.mkLink(self.assetsEntry)

            entries = await dag.list(path='blog')
            bEntries = entries if isinstance(entries, list) else []

            for entry in bEntries:
                await op.sleep()

                if entry == TAGS_NODEKEY:
                    continue

                nList = await dag.list(path='blog/{}'.format(entry))

                postObj = await dag.get('blog/{0}/{1}'.format(
                    entry, POST_NODEKEY))

                if not isinstance(postObj, dict):
                    continue

                post = postObj['blogpost']

                blogPosts.append(post)

                if 'view' in nList and assetsChanged is False:
                    continue

                self.dagBlog[entry]['view'] = await self.renderLink(
                    'usersite/blog_post.html',
                    contained=True,
                    post=post,
                )

            blogPosts = sorted(blogPosts,
                               key=lambda post: post['date_published'],
                               reverse=True)

            self.feedAddPosts(blogPosts, feed)

            requests = await dag.get(PINREQS_NODEKEY)

            if requests:
                for idx, request in enumerate(requests):
                    path = '{0}/{1}'.format(PINREQS_NODEKEY, idx)
                    if not await dag.get(
                            '{path}/view'.format(path=path, idx=idx)):
                        self.dagRequests[idx]['view'] = \
                            await self.renderLink(
                                'usersite/pinrequest.html',
                                request=request
                        )

                self.feedAddPinRequests(requests, feed)

            dag.root['pinrequests.html'] = await self.renderLink(
                'usersite/pinrequests.html',
                pinrequests=requests if requests else []
            )

            dag.root['index.html'] = await self.renderLink(
                'usersite/home.html',
                posts=blogPosts
            )

            dag.root['about.html'] = await self.renderLink(
                'usersite/about.html')

            # Finally, generate the Atom feed and put it in the graph
            try:
                atomFeed = feed.atom_str(pretty=True)
                entry = await op.addBytes(atomFeed)
                if entry:
                    # Unpin the old feed (disabled for now)
                    if self._atomFeedFn in dag.root and 0:
                        resolved = await dag.resolve(
                            path=self._atomFeedFn)
                        if resolved:
                            ensure(op.unpin(resolved))

                    dag.root[self._atomFeedFn] = dag.mkLink(entry)
            except Exception as err:
                log.debug('Error generating Atom feed: {}'.format(
                    str(err)))

            metadata = await dag.siteMetadata()
            metadata['date_updated'] = now.isoformat()
            dag.root[METADATA_NODEKEY] = metadata

        self.websiteUpdated.emit()
        self._updating = False

    def feedAddPinRequests(self, requests, feed):
        for id, reqobj in enumerate(requests):
            req = reqobj['pinrequest']
            rpath = self.sitePath.child(os.path.join(
                PINREQS_NODEKEY, str(id), 'view'))

            fEntry = feed.add_entry()
            fEntry.title('Pin request: {}'.format(req['title']))
            fEntry.id(rpath.dwebUrl)
            fEntry.link(href=rpath.dwebUrl, rel='alternate')
            fEntry.published(req['date_published'])
            fEntry.author({'name': self.profile.userInfo.username})

    def feedAddPosts(self, blogPosts, feed):
        for post in blogPosts:
            ppath = self.sitePath.child(os.path.join(
                'blog', post['postname'], 'view'))

            fEntry = feed.add_entry()
            fEntry.title(post['title'])
            fEntry.id(ppath.dwebUrl)
            fEntry.link(href=ppath.dwebUrl, rel='alternate')
            fEntry.updated(post['date_modified'])
            fEntry.published(post['date_published'])
            fEntry.author({'name': self.profile.userInfo.username})

            for tag in post['tags']:
                fEntry.category(term=tag)

    async def tmplRender(self, tmpl, contained=False, **kw):
        coro = render.ipfsRender if not contained else \
            render.ipfsRenderContained

        return await coro(self._jinjaEnv,
                          tmpl,
                          profile=self.profile,
                          dag=self.edag.dagRoot,
                          siteIpns=self.ipnsKey,
                          atomFeedrUrl=self.atomFeedPath.dwebUrl,
                          **kw)

    async def renderLink(self, tmpl, contained=False, **kw):
        # Render and link in the dag
        result = await self.tmplRender(tmpl, contained=contained, **kw)
        return self.edag.mkLink(result)
