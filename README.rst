
.. image:: https://gitlab.com/galacteek/galacteek/raw/master/share/icons/galacteek-incandescent-128.png
    :align: center
    :width: 64
    :height: 64

:info: A multi-platform browser for the distributed web

.. image:: https://travis-ci.org/pinnaculum/galacteek.svg?branch=master
    :target: https://travis-ci.org/pinnaculum/galacteek

**galacteek** is an experimental multi-platform Qt5-based browser/toolbox
for the IPFS_ peer-to-peer network.

Platforms supported
===================

- Linux (main target)
- MacOS
- FreeBSD (or any BSD OS, as long as you have PyCryptodome)

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

If you use any other system or want to install the software
manually you can always install from PyPI.

PyPI
----

You need to have python>=3.6 and pip installed.
From a virtualenv, or as root, install with:

.. code-block:: shell

    pip install galacteek

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
MIME type detection will be faster if you install **libmagic**. The
**zbar** library (for QR codes) is now embedded in the DMG.

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

Features
========

**galacteek** can either spawn an IPFS daemon and use it as transport, or
connect to an existing IPFS daemon. By default it will try to run a daemon. You
can change the IPFS connection settings by clicking on the settings icon in the
toolbar and restart the application afterwards. If using a custom daemon, you
should enable pubsub and p2p streams, or some features won't be available.

- Decentralized Identifiers (DID) support with IPID_
- Browser-to-browser DID authentication over libp2p streams
  (Verifiable Credentials with RSA-PSS)
- Browsing sessions with automatic pinning (pins every page you browse)
- File manager with drag-and-drop support
- Run WASM binaries with wasmer_ (use *Open* on a WASM object from the
  clipboard manager)
- Search content with the ipfs-search_ search engine
- Atom feeds (subscribe to feeds on the dweb)
- ENS_ (Ethereum Name Service) resolving (access to ENS+IPFS websites)
- Sharing hashmarks over pubsub
- Basic built-in media player with IPFS-stored playlists
- Image viewer
- QR codes from images

URL schemes
===========

As much as possible we're trying to follow the in-web-browsers_ specs
(URL notations are taken from there).

See urlschemes_ for more details.

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

Contributions
=============

Code contributions that can help:

- Write DID services (a chat service using JSON-LD for example)

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
.. _urlschemes: https://github.com/pinnaculum/galacteek/blob/master/galacteek/docs/manual/en/browsing.rst#supported-url-formats
.. _releases: https://github.com/pinnaculum/galacteek/releases
.. _ENS: https://ens.domains/
.. _in-web-browsers: https://github.com/ipfs/in-web-browsers
.. _AppImage: https://appimage.org/
.. _IPID: https://github.com/jonnycrunch/ipid
.. _wasmer: https://wasmer.io/
