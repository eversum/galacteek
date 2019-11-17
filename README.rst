
.. image:: https://gitlab.com/galacteek/galacteek/raw/master/share/icons/galacteek-incandescent-128.png
    :align: center
    :width: 64
    :height: 64

:info: A multi-platform browser for the distributed web

.. image:: https://travis-ci.org/pinnaculum/galacteek.svg?branch=master
    :target: https://travis-ci.org/pinnaculum/galacteek
.. image:: https://raw.githubusercontent.com/pinnaculum/galacteek/raw/master/share/icons/donate.png
    :target: https://github.com/sponsors/pinnaculum

**galacteek** is a multi-platform Qt5-based browser/toolbox
for the IPFS_ peer-to-peer network.

Installation
============

* **AppImage (Linux)**: `Galacteek-0.4.21-x86_64.AppImage <https://github.com/pinnaculum/galacteek/releases/download/v0.4.21/Galacteek-0.4.21-x86_64.AppImage>`_
* **DMG (MacOS)**: `Galacteek-0.4.21.dmg <https://github.com/pinnaculum/galacteek/releases/download/v0.4.21/Galacteek-0.4.21.dmg>`_

*On Linux*: Be sure to install all the **gstreamer** packages on your
system to be able to use the mediaplayer.

*On MacOS*: After opening/mounting the DMG image, hold Control and click on the
**galacteek** icon, and select **Open** and accept. You probably need to
allow the system to install applications *from anywhere* in the security
settings.

See the releases_ page for all releases.

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
- Distributed chat with pubsub (chat channels syncronized with CRDT+DAG)
- File manager with drag-and-drop support
- Run WASM binaries with wasmer_ (use *Open* on a WASM object from the
  clipboard manager)
- Search content with the ipfs-search_ search engine
- Atom feeds (subscribe to feeds on the dweb)
- ENS_ (Ethereum Name Service) resolving (access to ENS+IPFS websites)
- Basic built-in media player with IPFS-stored playlists
- Image viewer
- QR codes from images

Command-line usage
==================

Use the *-d* command-line switch to enable debugging output. Using *--profile* gives
you the ability to have separate application profiles (*main* is the default
profile). Use *--help* for all options.

Enable colorized log output with **--log-color**

Use the **--no-ipfsscheme-mutex** switch to disable mutexes in the native IPFS scheme
handler.

*Development*: Use *--monitor* to enable event-loop monitoring with aiomonitor_
(install aiomonitor_ manually as it's not a dependency).
Then connect to the aiomonitor_ interface with **nc localhost 50101**

Keyboard shortcuts
==================

Please see the shortcuts_ page (or from the application, click on the
Information icon in the toolbar, which will open the documentation).

Contributions
=============

Contributions that can help:

- Write DID services (a chat service using JSON-LD for example)
- Translations (french, spanish)

If you want to sponsor this project please use the
`Github Sponsors page <https://github.com/sponsors/pinnaculum>`_

Platforms supported
===================

- Linux (main target)
- MacOS
- FreeBSD (or any BSD OS, with manual build)

Requirements
============

- python3 >= 3.7
- go-ipfs_ >= 0.5.0
- PyQt5 >= 5.13.2
- PyQtWebengine >= 5.13.2
- gstreamer (on Linux) for media player support
- git
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
