=========
CHANGELOG
=========

0.4.9
=====

- deps: use web3
- ipfssearch UI: implement a simple page factory, serving
  pre-generated search pages.
- ipfssearch: communication on the webchannel has been
  simplified. Hits are sent on the channel as soon as they
  are received; the JS code stores them right away in the
  DOM (hidden) but only makes them visible when the hit is
  valid (= we can at least fetch the object stat). We fetch
  multiple pages per 'virtual' page

0.4.8
=====

- Add tox as part of the travis build
- Add an 'invalid item' signal in the clipboard manager
- bugfix in the 'IPNS follow' action

0.4.7
=====

- Implementation of native ({ipfs,ipns}://) URL scheme handlers
  using async reqs (with aioipfs, no gateway)

0.4.6
=====

- Implement ENS resolver (ens:// URLs are supported in the browser)
- Replace most asyncio.wait_for() calls by async_timeout (performance)
- General purpose database (URL history for now) with aiosqlite
- Add a PIN button in the image viewer

0.4.5
======

- deps: remove qreader
- deps: don't pin most dependencies
- deps: use PyQt 5.12.2, and PyQtWebengine 5.12
- deps: use Pygments, feedgen and feedparser for Atom feeds
- deps: use Markdown instead of markdown2
- move the ResourceAnalyzer to galacteek.core.analyzer
- user website's templates moved to galacteek/templates/usersite
- IPFS scheme handlers are implemented now in galacteek.core.schemes
- pretty much all content should now be imported in CIDv1
- ipfsops: new coros addBytes() and addString() (CIDv1 by default)
- the user's website now has a basic blog and an Atom feed
- galacteek.ipfs.dag.EvolvingDAG: some fixes and additions
- the application/atom+xml mime type should be correctly handled
- add a markdown reference help webpage
