
Application settings
====================

.. image:: ../../../../share/icons/settings.png
    :width: 64
    :height: 64

IPFS settings
-------------

The application can either spawn a local IPFS daemon (this is the default) or let
you use an IPFS daemon to which you already have access.

If the IPFS daemon cannot be started, it is possible that one of the listening
ports (API, swarm or HTTP gateway) is already being used on your system. In
that case, change the ports configuration in the settings and restart the
application.

The **Minimum swarm connections** and **Maximum swarm connections** settings
let you modify the number of connections to be used for the IPFS swarm.
Using low values can significantly reduce CPU usage.

The **Maximum storage** setting controls the maximum allowed IPFS repository
size in gigabytes.

The **Routing mode** setting lets you choose between *dht* (the default)
or *dhtclient*.  Using *dhtclient* can significantly reduce CPU usage, but
your node will not act as a full DHT node on the network.

**Note**: switching from a local to custom daemon (or vice versa) will make you
lose access to the content that you might have published using the previous
settings, so use with care. Use separate *application profiles* with the
**--profile** command-line switch to keep multiple separate profiles.

Ethereum settings
-----------------

In this section you can configure the Ethereum connection settings.
These settings are used by the *web3* web profile to provide
a web3.js *Web3* instance available as *window.web3* in the main
Javascript world.

User interface settings
-----------------------

Hide hashes
^^^^^^^^^^^

This will hide the IPFS hashes wherever possible (file manager, explorer..)

Wrap single files or directories
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If enabled, files or directories will be wrapped within a directory object
(.dirw)

Enable navigation history
^^^^^^^^^^^^^^^^^^^^^^^^^

If enabled, visited dweb and ENS URLs are recorded and you will get
history search results when typing an URL.

Default web profile
^^^^^^^^^^^^^^^^^^^

With this setting you can select which web profile you want enabled
by default when you open a browser tab. This setting is set by
default to *minimal*. If you want the IPFS Javascript API always
enabled you should select *ipfs* here.
