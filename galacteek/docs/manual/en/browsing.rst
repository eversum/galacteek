
Browsing
========

URL bar
-------

In the address bar you can type (or paste) a full URL, an
IPFS CID or a full IPFS path (they will be loaded with the
appropriate scheme).

You can also type words that you want to search for in the hashmarks
database and the visited URLs history (search results will
pop up after a short amount of time). Hitting the *Escape* key
will hide the results.

Supported URL formats
---------------------

ipfs:// and ipns://
^^^^^^^^^^^^^^^^^^^

These are the *native* URL schemes that support
using base32-encoded CIDv1 strings as hostname
(with the benefit of the CID becoming the URL's
authority). The following URL formats are supported::

    ipfs://{cidv1base32}/path/to/resource
    ipns://{fqdn-with-dnslink}/path/to/resource

Examples::

    ipfs://bafybeibp7sff6wwowsimitrxcpdoqnknyreesvtn24qrnx7gxkhqhzj2fi/
    ipns://ipfs.io/

If you use a valid base58-encoded CID (whatever the CID version)
with the *ipfs://* URL scheme, the CID will automatically be
upgraded (v0 to v1) if necessary and its base32 representation will
be used in the URL. For instance, trying to access::

    ipfs://QmXoypizjW3WknFiJnKLwHCnL72vedxjQkDDP1mXWo6uco

will trigger a CID upgrade and ultimately access the same object with
its base32 representation at the following URL::

    ipfs://bafybeiemxf5abjwjbikoz4mc3a3dla6ual3jsgpdr4cjr3oz3evfyavhwq

*Note*: the scheme handler for these URL schemes does not
use the *go-ipfs* daemon's HTTP gateway

dweb:/
^^^^^^

This is the legacy scheme and it will automatically be used when
accessing content rooted under CIDv0 objects.

Since version *0.4.12*, automatic CID upgrade is enabled as much
as possible, meaning that the *ipfs://* URL scheme will
automatically be used whenever possible.
IPNS paths using a base58 libp2p key will still be
accessed using this scheme.

Because it proxies the requests to the *go-ipfs* daemon's HTTP
gateway, it can handle anything that the daemon supports::

    dweb:/ipfs/{cidv0}/path/to/resource
    dweb:/ipfs/{cidv1b32}/path/to/resource
    dweb:/ipfs/{cidv1b58}/path/to/resource
    dweb:/ipns/{fqdn-with-dnslink}/path/to/resource
    dweb:/ipns/{libp2p-key-in-base58}/path/to/resource

Examples::

    dweb:/ipfs/bafybeibp7sff6wwowsimitrxcpdoqnknyreesvtn24qrnx7gxkhqhzj2fi
    dweb:/ipfs/QmXoypizjW3WknFiJnKLwHCnL72vedxjQkDDP1mXWo6uco/wiki/
    dweb:/ipns/QmarwvLcWm51SwhnxABxsy1cE7v1RHPMjt4VkQ3kqsrdX3
    dweb:/ipns/awesome.ipfs.io

ens://
^^^^^^

There is support for accessing IPFS-hosted websites that are registered
on the *Ethereum Name Service* (see ENS_). Just use **ens://mydomain.eth**
for example as a URL in the browser and you will be redirected to the IPFS
website referenced on ENS for this domain.

Go to `ens://blog.almonit.eth <ens://blog.almonit.eth>`_ to find a list
of some ENS+IPFS websites.

manual:/
^^^^^^^^

There is support for mapping IPFS objects to a specific URL scheme,
allowing easy access from the URL bar to commonly-accessed resources.

This is used for instance by the manual. To access the manual from
the URL bar, just type in **manual:/** (or just **manual:**)

- `manual:/ <manual:/>`_
- `manual:/browsing.html <manual:/browsing.html>`_

q://
^^^^

The **q://** URL scheme allows quick access to IPFS objects that
you've mapped from the browser. From a browser tab, open the IPFS
menu and select *Create quick-access mapping*. Once the object is
mapped, it will be accessible with the **q://mappingname** URL,
for instance if your mapping name is *docs*, the quick-access URL
would be **q://docs**

If you are mapping an IPNS path, it is resolved periodically
and the result is cached.

Web profiles
------------

There are 3 distinct web profiles that can be used when accessing a
webpage. The current profile can be changed from a browser tab by
opening the IPFS menu and selecting a profile from the *Web profile*
submenu.

You can change the default web profile that will be used when opening
a browser tab by changing the *Default web profile* setting in the *UI*
section of the application settings.

Minimal profile
^^^^^^^^^^^^^^^

This profile doesn't include any specific scripts

IPFS profile
^^^^^^^^^^^^

This profile adds a JS script to be able to access your IPFS node
from *window.ipfs* in the main Javascript world

Web3 profile
^^^^^^^^^^^^

Derives from the IPFS profile. If Ethereum is enabled, it injects
a *Web3* instance (from the *web3.js* JS library) available as
*window.web3* in the main Javascript world

.. _ENS: https://ens.domains/
