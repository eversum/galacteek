import os.path
import uuid
import pkg_resources
from datetime import datetime
from datetime import timezone

from feedgen.feed import FeedGenerator

from galacteek import log
from galacteek import logUser
from galacteek import ensure
from galacteek import AsyncSignal
from galacteek.ipfs import ipfsOp
from galacteek.ipfs.stat import StatInfo
from galacteek.ipfs.cidhelpers import ipnsKeyCidV1
from galacteek.ipfs.cidhelpers import IPFSPath
from galacteek.ipfs.cidhelpers import joinIpns
from galacteek.ipfs.cidhelpers import stripIpfs
from galacteek.core.analyzer import ResourceAnalyzer
from galacteek.core import isoformat
from galacteek.dweb import render
from galacteek.dweb.markdown import markitdown
from galacteek.dweb.atom import DWEB_ATOM_FEEDFN
from galacteek.dweb.atom import DWEB_ATOM_FEEDGWFN

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


class UserWebsite:
    """
    The website associated to the user.

    Later on this should become more generic to create all kinds of apps
    """

    websiteUpdated = AsyncSignal()

    def __init__(self, edag, profile, ipnsKeyId, jinjaEnv, parent=None):
        self._profile = profile
        self._ipnsKeyId = ipnsKeyId
        self._edag = edag
        self._jinjaEnv = jinjaEnv

        self._atomFeedFn = DWEB_ATOM_FEEDFN
        self._atomFeedGwFn = DWEB_ATOM_FEEDGWFN

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
        return self.sitePath.ipfsUrl

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
        return self.dagRoot[BLOG_NODEKEY]

    def debug(self, msg):
        return self.profile.debug(msg)

    @ipfsOp
    async def blogEntries(self, op):
        listing = await self.edag.list(path=BLOG_NODEKEY)
        return [entry for entry in listing if entry != 'index.html' and
                not entry.startswith('_')]

    @ipfsOp
    async def blogPost(self, ipfsop, title, msg, category=None,
                       tags=None, author=None):
        async with self.edag:
            sHandle = self.profile.userInfo.spaceHandle

            username = sHandle.short
            uid = str(uuid.uuid4())
            postName = title.strip().lower().replace(' ', '-')

            exEntries = await self.blogEntries()
            if postName in exEntries:
                raise Exception(
                    'A blog post with this name already exists')

            now = datetime.now(timezone.utc)

            postObject = {
                'blogpost': {
                    'authordid': self.profile.userInfo.personDid,
                    'body': msg,
                    'title': title,
                    'uuid': uid,
                    'postname': postName,  # name of the post's DAG node
                    'tags': tags if tags else [],
                    'category': None,
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
        await ipfsop.sleep(1)

        result = await self.dagUser.resolve(
            os.path.join(BLOG_NODEKEY, postName, 'view'))
        resolved = IPFSPath(result, autoCidConv=True)

        if isinstance(tags, list) and resolved.isIpfsRoot and resolved.valid:
            # Register the post by tag

            async with self.edag as dag:
                byTags = dag.root[BLOG_NODEKEY][TAGS_NODEKEY]

                for tag in tags:
                    if tag is None:
                        continue

                    planet, ptag = tag.split('#')
                    if not planet or not ptag:
                        continue

                    planet = planet.replace('@', '')

                    byTags.setdefault(planet, {})
                    byTags[planet].setdefault(ptag, {
                        '_posts': []
                    })

                    byTags[planet][ptag]['_posts'].append({
                        'name': postName,
                        'title': title,
                        'view': {
                            '/': stripIpfs(str(resolved))
                        }
                    })
                    byTags[planet][ptag]['index.html'] = await self.renderLink(
                        'usersite/bytag.html',
                        contained=True,
                        tag=tag,
                        tagposts=byTags[planet][ptag]['_posts']
                    )

        logUser.info('Your blog post is online')
        return True

    @ipfsOp
    async def makePinRequest(self, op, title, descr, objects,
                             priority=0, tags=None):
        async with self.profile.dagUser as dag:
            # objects needs to be a list of IPFS objects paths

            if not isinstance(objects, list):
                return False

            username = self.profile.userInfo.iphandle
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

        if self.profile.ctx.hasRsc('ipfs-cube-64'):
            self.edag.root['media']['images']['ipfs-cube.png'] = \
                self.edag.mkLink(self.profile.ctx.resources['ipfs-cube-64'])
        if self.profile.ctx.hasRsc('atom-feed'):
            self.edag.root['media']['images']['atom-feed.png'] = \
                self.edag.mkLink(self.profile.ctx.resources['atom-feed'])

        self.edag.root['about.html'] = await self.renderLink(
            'usersite/about.html')

    def createFeed(self, ftype='ipfs'):
        # Create the feed

        sHandle = self.profile.userInfo.spaceHandle

        feed = FeedGenerator()
        feed.id(self.siteUrl)
        feed.title("{0}'s dweb space".format(sHandle.short))
        feed.author({
            'name': self.profile.userInfo.iphandle
        })

        if ftype == 'ipfs':
            feed.link(href=self.atomFeedPath.ipfsUrl, rel='self')
        elif ftype == 'publicgw':
            feed.link(href=self.atomFeedPath.publicGwUrl, rel='self')

        feed.language('en')
        return feed

    async def updateAboutPage(self):
        async with self.profile.dagUser as dag:
            dag.root['about.html'] = await self.renderLink(
                'usersite/about.html')
            dag.root['media']['images']['avatar'] = \
                self.profile.userInfo.avatar

        await self.websiteUpdated.emit()

    @ipfsOp
    async def update(self, op):
        if self.dagRoot is None or self.updating is True:
            return

        now = datetime.now(timezone.utc)
        self._updating = True

        assetsChanged = False
        blogPosts = []

        feed = self.createFeed()
        feedgw = self.createFeed(ftype='publicgw')

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
            self.feedAddPosts(blogPosts, feedgw, ftype='publicgw')

            requests = await dag.get(PINREQS_NODEKEY)

            if requests:
                for idx, request in enumerate(requests):
                    path = '{0}/{1}'.format(PINREQS_NODEKEY, idx)
                    if not await dag.get(
                            '{path}/view'.format(path=path)):
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
                'usersite/home.html'
            )

            self.dagBlog['index.html'] = await self.renderLink(
                'usersite/blog.html',
                posts=blogPosts
            )

            dag.root['about.html'] = await self.renderLink(
                'usersite/about.html')

            # Finally, generate the Atom feed and put it in the graph
            try:
                atomFeed = feed.atom_str(pretty=True)
                entry = await op.addBytes(atomFeed)
                atomFeedGw = feedgw.atom_str(pretty=True)
                entryGw = await op.addBytes(atomFeedGw)

                if entry:
                    # Unpin the old feed (disabled for now)
                    if self._atomFeedFn in dag.root and 0:
                        resolved = await dag.resolve(
                            path=self._atomFeedFn)
                        if resolved:
                            ensure(op.unpin(resolved))

                    dag.root[self._atomFeedFn] = dag.mkLink(entry)

                if entryGw:
                    dag.root[self._atomFeedGwFn] = dag.mkLink(entryGw)
            except Exception as err:
                log.debug('Error generating Atom feed: {}'.format(
                    str(err)))

            metadata = await dag.siteMetadata()
            metadata['date_updated'] = now.isoformat()
            dag.root[METADATA_NODEKEY] = metadata

        await self.websiteUpdated.emit()
        self._updating = False

    def feedAddPinRequests(self, requests, feed):
        for id, reqobj in enumerate(requests):
            req = reqobj['pinrequest']
            rpath = self.sitePath.child(os.path.join(
                PINREQS_NODEKEY, str(id), 'view'))

            fEntry = feed.add_entry()
            fEntry.title('Pin request: {}'.format(req['title']))
            fEntry.id(rpath.ipfsUrl)
            fEntry.link(href=rpath.ipfsUrl, rel='alternate')
            fEntry.published(req['date_published'])
            fEntry.author({'name': self.profile.userInfo.iphandle})

    def feedAddPosts(self, blogPosts, feed, ftype='ipfs'):
        for post in blogPosts:
            ppath = self.sitePath.child(os.path.join(
                'blog', post['postname'], 'view'))

            fEntry = feed.add_entry()
            fEntry.title(post['title'])

            if ftype == 'ipfs':
                url = ppath.ipfsUrl
            elif ftype == 'publicgw':
                url = ppath.publicGwUrl

            fEntry.id(url)
            fEntry.link(href=url, rel='alternate')
            fEntry.updated(post['date_modified'])
            fEntry.published(post['date_published'])
            fEntry.content(
                content=markitdown(post['body']),
                type='html'
            )

            fEntry.author({'name': self.profile.userInfo.iphandle})

            for tag in post['tags']:
                fEntry.category(term=tag)

    async def tmplRender(self, tmpl, contained=False, **kw):
        coro = render.ipfsRender if not contained else \
            render.ipfsRenderContained

        ipnsKeyV1 = ipnsKeyCidV1(self.ipnsKey)

        return await coro(self._jinjaEnv,
                          tmpl,
                          profile=self.profile,
                          dag=self.edag.dagRoot,
                          siteIpns=ipnsKeyV1,
                          atomFeedrUrl=self.atomFeedPath.ipfsUrl,
                          **kw)

    async def renderLink(self, tmpl, contained=False, **kw):
        # Render and link in the dag
        result = await self.tmplRender(tmpl, contained=contained, **kw)
        return self.edag.mkLink(result)
