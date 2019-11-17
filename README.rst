
.. image:: https://gitlab.com/galacteek/galacteek/raw/master/share/icons/galacteek-incandescent.png
    :align: center
    :width: 128
    :height: 128

:info: A multi-platform browser for the distributed web

.. image:: https://travis-ci.org/pinnaculum/galacteek.svg?branch=master
    :target: https://travis-ci.org/pinnaculum/galacteek

**galacteek** is an experimental multi-platform Qt5-based browser/toolbox
for the IPFS_ peer-to-peer network.

Platforms supported
===================

- Linux (main target)
- FreeBSD (or any BSD OS, as long as you have PyCryptodome)
- MacOS

This started as an experiment with quamash_ and is WIP.

Please prefer the ready-to-use images over a manual install
if available on your platform, as they contain everything
needed, including the latest go-ipfs_ binary.

Installation
============

If you use Linux or MacOS you can download a prebuilt image
(an AppImage for Linux or a .dmg image for osx) from the releases_
page.

The main images are built from the *master* branch. Latest
(development) images are built from the *pimp-my-dweb* branch.
They contain new features like DID (IPID) support.

If you want to use QR codes on MacOS, don't forget to install
zbar by running **brew install zbar** in a terminal.

If you use any other system or want to install the software
manually you can always install from PyPI.

PyPI
----

You need to have python>=3.6 and pip installed.
From a virtualenv, or as root, install with:

.. code-block:: shell

    pip install galacteek

Upgrade with:

.. code-block:: shell

    pip install -U galacteek

Or building it from source:

.. code-block:: shell

    pip install -r requirements.txt
    python setup.py build install

Now just run the application with:

.. code-block:: shell

    galacteek

If you don't have go-ipfs_ already installed, the application will ask you
if you want to automatically download it from dist.ipfs.io_
You need a recent version of go-ipfs_ (> 0.4.7) with the new DAG API.

For the media player to work on Linux, you will need to install the
*gstreamer* (1.x) package and all the gstreamer plugins.

There is experimental support for reading QR codes containing IPFS addresses,
using pyzbar_. pyzbar_ depends on the zbar shared library,
so make sure it's installed on your system (on Linux look for a libzbar or
libzbar0 package and install it, on MacOS install it with
**brew install zbar**).

AppImage
--------

For Linux users (arch: *x86_64*), you can get an AppImage_
from the releases_ page. The script used to build the image can be found
`here <https://github.com/pinnaculum/galacteek/blob/master/AppImage/galacteek-appimage-build>`_

DMG (MacOS)
-----------

On MacOS the easiest is to download a DMG image from the releases_ page.
MIME type detection will be faster if you install **libmagic**. Install
**zbar** as well for QR codes if you want with::

    brew install libmagic zbar

After opening/mounting the DMG image, hold Control and click on the
**galacteek** icon, and select **Open** and accept. You probably need to
allow the system to install applications *from anywhere* in the security
settings.

Command-line usage
==================

Use the *-d* command-line switch to enable debugging output. Using *--profile* gives
you the ability to have separate application profiles (*main* is the default
profile). Use *--help* for all options.

Use the **--no-ipfsscheme-mutex** switch to disable mutexes in the native IPFS scheme
handler.

*Development*: Use *--monitor* to enable event-loop monitoring with aiomonitor_
(install aiomonitor_ manually as it's not a dependency).
Then connect to the aiomonitor_ interface with **nc localhost 50101**

URL schemes
===========

As much as possible we're trying to follow the in-web-browsers_ specs
(URL notations are taken from there).

ipfs:// and ipns://
-------------------

These are what could be considered the *native* schemes.
The scheme handler for these schemes supports the following
URL formats::

    ipfs://{cidv1base32}/path/to/resource
    ipns://{fqdn-with-dnslink}/path/to/resource

This scheme handler makes the requests asynchronously on the daemon
(it does not use the go-ipfs's HTTP gateway). The root CID or IPNS
domain of the URL is considered the authority.

We are using CIDv1 by default for all content (and starting with
go-ipfs_ v0.4.21, they will be base32-encoded by default). If you're
accessing an object within a base58-encoded CIDv1, the root CID will
automatically be converted to its base32 representation so that you can
use the native *ipfs://* scheme. 

When you are using the native handler, the URL's background color should
change (you're using base32 after all!) and will look something like this:

.. image:: https://gitlab.com/galacteek/galacteek/raw/master/screenshots/ipfs-scheme-urlbar.png
    :align: center

*Note*: this is a recent implementation, please report any issues.
MIME type detection for rendered resources could be slow on
platforms that don't have libmagic.

dweb:/
------

This is the legacy scheme and it will be automatically used when
accessing content rooted under CIDv0 objects.
Because it proxies the requests to the daemon's HTTP gateway, it
can handle anything that the daemon supports::

    dweb:/ipfs/{cidv0}/path/to/resource
    dweb:/ipfs/{cidv1b32}/path/to/resource
    dweb:/ipfs/{cidv1b58}/path/to/resource
    dweb:/ipns/{fqdn-with-dnslink}/path/to/resource
    dweb:/ipns/{libp2p-key-in-base58}/path/to/resource

ens://
------

There is support for accessing IPFS-hosted websites that are registered
on the *Ethereum Name Service* (see ENS_). Just use **ens://mydomain.eth**
for example as a URL in the browser and you will be redirected to the IPFS
website referenced on ENS for this domain.

Go to **ens://blog.almonit.eth** to find a list of some ENS+IPFS websites.

Features
========

**galacteek** can either spawn an IPFS daemon and use it as transport, or
connect to an existing IPFS daemon. By default it will try to run a daemon. You
can change the IPFS connection settings by clicking on the settings icon in the
toolbar and restart the application afterwards. If using a custom daemon, you
should enable pubsub or some features won't be available.

- Browsing sessions with automatic pinning (pins every page you browse)
- File manager with drag-and-drop support
- Search content with the ipfs-search_ search engine
- Atom feeds (subscribe to feeds on the dweb)
- ENS_ (Ethereum Name Service) resolving (access to ENS+IPFS websites)
- Sharing hashmarks over pubsub
- Basic built-in media player with IPFS-stored playlists
- Image viewer
- QR codes from images
- Decentralized application development/testing with the Javascript API
  (using *window.ipfs*)

Keyboard shortcuts
==================

Please see the shortcuts_ page (or from the application, click on the
Information icon in the toolbar, which will open the documentation).

Screenshots
===========

.. figure:: https://gitlab.com/galacteek/galacteek/raw/master/screenshots/browse-wikipedia-small.png
    :target: https://gitlab.com/galacteek/galacteek/raw/master/screenshots/browse-wikipedia.png
    :align: center
    :alt: Browsing the Wikipedia mirror over IPFS

    Browsing the Wikipedia mirror over IPFS

.. figure:: https://gitlab.com/galacteek/galacteek/raw/master/screenshots/qr-codes-mezcla.png
    :target: https://gitlab.com/galacteek/galacteek/raw/master/screenshots/qr-codes-mezcla.png
    :align: center
    :alt: QR codes

    IPFS QR codes

Contributions and contact
=========================

Contributions and ideas are more than welcome!
Contact by mail at: galacteek AT protonmail DOT com

If you want to donate to this project please use the
`Patreon page <https://www.patreon.com/galacteek>`_

Requirements
============

- python3 >= 3.6
- go-ipfs_ >= 0.4.7
- PyQt5 >= 5.12.2
- PyQtWebengine >= 5.12
- gstreamer (on Linux) for media player support
- quamash_
- aiohttp_
- aioipfs_

License
=======

**galacteek** is offered under the GNU GPL3 license

The logos and animations are licensed under the Creative
Commons CC-BY-SA license.

Some elements from the ipfs-css_ repository (CSS files and fonts) are included.

Some icons from the "Oxygen" icons set are included.

Some of the beautiful artwork (under the Creative Commons CC-BY-SA license)
from the ipfs-logo_ project's repository is included, unchanged.

.. _aiohttp: https://pypi.python.org/pypi/aiohttp
.. _aioipfs: https://gitlab.com/cipres/aioipfs
.. _aiomonitor: https://github.com/aio-libs/aiomonitor
.. _quamash: https://github.com/harvimt/quamash
.. _go-ipfs: https://github.com/ipfs/go-ipfs
.. _dist.ipfs.io: https://dist.ipfs.io
.. _IPFS: https://ipfs.io
.. _ipfs-logo: https://github.com/ipfs/logo
.. _ipfs-search: https://ipfs-search.com
.. _ipfs-css: https://github.com/ipfs-shipyard/ipfs-css
.. _releases: https://github.com/pinnaculum/galacteek/releases
.. _srip: https://www.flaticon.com/authors/srip
.. _pyzbar: https://github.com/NaturalHistoryMuseum/pyzbar/
.. _qreader: https://github.com/ewino/qreader/
.. _shortcuts: http://htmlpreview.github.io/?https://raw.githubusercontent.com/pinnaculum/galacteek/master/galacteek/docs/manual/en/html/shortcuts.html
.. _releases: https://github.com/pinnaculum/galacteek/releases
.. _ENS: https://ens.domains/
.. _in-web-browsers: https://github.com/ipfs/in-web-browsers
.. _AppImage: https://appimage.org/
