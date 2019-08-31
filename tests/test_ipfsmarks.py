import pytest


from galacteek.core.ipfsmarks import *


@pytest.fixture
def bmarks(tmpdir):
    return IPFSMarks(str(tmpdir.join('bm')))


@pytest.fixture
def bmarks2(tmpdir):
    return IPFSMarks(str(tmpdir.join('bm2')))


class TestMarks:
    @pytest.mark.parametrize(
        'path1,path2,path3,path4',
        [
            ('/ipfs/QmT1TPVjdZ9CRnqwyQ9WygDoRgRRibFrEyWufenu92SuUV/',
             '/ipfs/QmT1TPVjdZ9CRnqwyQ9WygDoRgRRibFrEyWufenu92SuUV/a/abcdef',
             '/ipfs/Qma1TPVjdZ9CReqwyQ9Wvv3oRgRRi5FrEyWufenu92SuUV/www/',
             '/ipfs/Qma8TPVjdZ3CReqwyQ9Wvv3oggRRi3FrEyWufenu92SuUV/src/',
             )])
    @pytest.mark.parametrize('title', ['Broken glass'])
    def test_simpleadd(self, bmarks, path1, path2, path3, path4, title):
        assert bmarks.add(path1, title=title, tags=['dev'])
        assert bmarks.add(path1, title=title) is False
        assert bmarks.add(path2, title=title)

        assert bmarks.isInCategory('general', path1) is True

        marks = bmarks.getCategoryMarks('general')
        for path, mark in marks.items():
            assert mark['metadata']['title'] == title

        assert bmarks.add(path3, title='Random', category='no/way')
        assert bmarks.add(path4, title='Src directory',
                          description='Some code',
                          category='code/src')
        assert bmarks.isInCategory('code/src', path4) is True
        assert bmarks.isInCategory('code/src', path1) is False

        assert bmarks.find(path1) is not None
        assert bmarks.find(path3).path == path3

        assert bmarks.delete(path2) is not None
        assert bmarks.find(path2) is None

        assert bmarks.searchByMetadata({
            'title': 'Rand.*'
        }).path == path3

        mark = bmarks.searchByMetadata({
            'description': 'Some.*'
        })
        assert mark.path == path4

        assert bmarks.add(path2, title=title)

        mark = bmarks.find(path1)
        assert mark.markData['metadata']['title'] == title

        bmarks.addCategory('tests', parent=None)
        cats = bmarks.getCategories()
        assert 'general' in cats
        assert 'tests' in cats
        assert 'no/way' in cats

        bmarks.dump()

    @pytest.mark.parametrize(
        'path1,path2,path3',
        [
            ('/ipfs/QmT1TPVjdZ9CRnqwyQ9WygDoRgRRibFrEyWufenu92SuUV/',
             '/ipfs/QmT1TPVjdZ9CRnqwyQ9WygDoRgRRibFrEyWufenu92SuUV/a/abcdef',
             '/ipfs/Qma1TPVjdZ9CReqwyQ9Wvv3oRgRRi5FrEyWufenu92SuUV/www/')])
    @pytest.mark.parametrize('title', ['Smooth ride'])
    def test_merge(self, bmarks, bmarks2, path1, path2, path3, title):
        bmarks.add(path1, title=title, tags=['dev'])
        bmarks2.add(path2, category='www/sub/cat', title=title)
        bmarks2.add(path3, category='www/other', title=title)
        bmarks.merge(bmarks2)

        assert bmarks.find(path2) is not None
        assert bmarks.find(path3) is not None

        bmarks2.add(path3, category='www/other', title=title)
        bmarks.dump()

    @pytest.mark.parametrize('feed1,mark1', [
        (
            '/ipns/QmT1TPVjdZ9CvngwyQ9WygDoRgRRibFrEyWufenu92SuUV',
            '/ipfs/QmT1TPVjdZ9CvngwyQ9WygDoRgRRibFrEyWufenu92SuUb',
        )])
    def test_follow(self, bmarks, feed1, mark1):
        bmarks.follow(feed1, 'test', resolveevery=60)
        bmarks.feedAddMark(feed1, IPFSHashMark.make(mark1, title='ok'))
        assert bmarks.feedAddMark(
            feed1, IPFSHashMark.make(
                mark1, title='ok2')) is False
        bmarks.dump()

    @pytest.mark.parametrize('path1,path2', [
        (
            '/ipfs/QmT1TPVjdZ9CRnqwyQ9WygDoRgRRibFrEyWufenu92SuUV',
            '/ipfs/Qma1TPVjdZ9CReqwyQ9Wvv3oRgRRi5FrEyWufenu92SuUV/www'
        )])
    @pytest.mark.parametrize('title', ['Broken glass'])
    @pytest.mark.asyncio
    async def test_mergeshared(self, event_loop, bmarks, bmarks2,
                               path1, path2, title):
        assert bmarks.add(path1, title=title, share=True, pinSingle=True)
        assert bmarks.add(path2, title=title, share=True, pinRecursive=True)
        bmarks2.merge(bmarks, share=True, reset=True)


class TestHashPlones:
    @pytest.mark.parametrize(
        'path1,path2,path3',
        [
            ('/ipfs/QmT1TPVjdZ9CRnqwyQ9WygDoRgRRibFrEyWufenu92SuUV',
             '/ipfs/QmT1TPVjdZ9CRnqwyQ9WygDoRgRRibFrEyWufenu92SuUV/a/abcdef',
             '/ipfs/QmT1TPVjdZ9CRnqwyQ9WygDoRgRRibFrEyWufenu92SuUV/b/ogkush')])
    def test_hashpyramidadd(self, qtbot, bmarks, path1, path2, path3):
        def pyramidAdded(path, mark):
            assert isinstance(mark, IPFSHashMark)

        bmarks.pyramidAddedMark.connect(pyramidAdded)

        with qtbot.waitSignal(bmarks.pyramidConfigured, timeout=2000):
            pyramid = bmarks.pyramidNew('pyramid1', 'my/pyramids', path1,
                                        ipnskey='abcd', description='Pyramid1')

        with qtbot.waitSignal(bmarks.pyramidAddedMark, timeout=2000):
            pyramid = bmarks.pyramidAdd('my/pyramids/pyramid1', path1)
            mark = bmarks.pyramidGetLatestHashmark('my/pyramids/pyramid1')
            assert mark.path == path1

            pyramid = bmarks.pyramidAdd('my/pyramids/pyramid1', path2)
            mark = bmarks.pyramidGetLatestHashmark('my/pyramids/pyramid1')
            assert mark.path == path2

        with qtbot.waitSignal(bmarks.pyramidNeedsPublish, timeout=2000):
            pyramid = bmarks.pyramidAdd('my/pyramids/pyramid1', path3)

        pyramid = bmarks.pyramidGet('my/pyramids/pyramid1')
        assert pyramid.marksCount == 3
        bmarks.pyramidPop('my/pyramids/pyramid1')
        assert pyramid.marksCount == 2
        assert pyramid.latest == path2

        bmarks.dump()
