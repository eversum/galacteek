
Browsing
========

URL bar
-------

In the address bar you can type (or paste) a full URL, or
type words that you want to search for in the hashmarks
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

*Note*: the scheme handler for these URL schemes does not
use the daemon's HTTP gateway

dweb:/
^^^^^^

This is the legacy scheme and it will be automatically used when
accessing content rooted under CIDv0 objects.
Because it proxies the requests to the daemon's HTTP gateway, it
can handle anything that the daemon supports::

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

Go to **ens://blog.almonit.eth** to find a list of some ENS+IPFS websites.

Other
^^^^^

There is support for mapping IPFS objects to a specific URL scheme,
allowing easy access from the URL bar to commonly-accessed resources.

Right now this is only used for the manual. To access the manual from
the URL bar, just type in **manual:/** (or just **manual:**)

- `manual:/ <manual:/>`_
- `manual:/browsing.html <manual:/browsing.html>`_

Web profiles
------------

There are 3 distinct web profiles that can be used when accessing a
webpage. The current profile can be changed from a browser tab by
opening the IPFS menu and selecting a profile from the *Web profile*
submenu.

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
a *web3.js* instance available as *window.web3* in the main
Javascript world

.. _ENS: https://ens.domains/
