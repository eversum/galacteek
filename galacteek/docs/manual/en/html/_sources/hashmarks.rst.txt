.. _hashmarks:

Hashmarks
=========

Hashmarks are bookmarks for IPFS objects (that can be links to
directories, webpages, documents, text files, ...). Hashmarks
are referenced by the full IPFS path of the object and can contain
*fragments*.  These are all valid paths for hashmarks::

    /ipfs/zdj7WazZDaMUSua3wCKgjPAj9bZXbh2EMUHzFTEmHh1BUs2uH
    /ipfs/zdj7WazZDaMUSua3wCKgjPAj9bZXbh2EMUHzFTEmHh1BUs2uH/settings.html
    /ipfs/zdj7WazZDaMUSua3wCKgjPAj9bZXbh2EMUHzFTEmHh1BUs2uH/settings.html#ipfs-settings
    /ipns/dist.ipfs.io/favicon.ico

You can create hashmarks from many places, like in a browser tab,
or from the filemanager.

Pressing **Ctrl+b** from the browser will hashmark the current
page if it's a valid IPFS object. From the clipboard manager
you can create hashmarks as well, by opening the menu of the
clipboard item of your choice and clicking on the *Hashmark* action.

Hashmarks are given a category, a title, description and icon (that
will be stored within IPFS). Flagging a hashmark as *shared* means
that it will be shared on the network with other peers (off by default).
Received hashmarks are RSA-encrypted in your IPFS repository with
your profile's RSA key, and searchable from the hashmarks library.

Local Hashmarks menu
--------------------

.. image:: ../../../../share/icons/hashmarks.png
    :width: 64
    :height: 64

From the toolbar, clicking on the hashmarks icon opens a menu
giving access to all your local hashmarks, by category.

Clicking an item will trigger the opening of the corresponding
object, depending on its type (the file type of the object
is automatically detected and cached by the application). There
are built-in viewers/renderers for things like text files,
images, multimedia files etc.. For files that cannot be
rendered by the application (for example PDF files), the system's
default application will be used to open the file.

Searching
---------

.. image:: ../../../../share/icons/hashmarks-library.png
    :width: 64
    :height: 64

The hashmarks library button gives you the ability to search
for content in the global hashmarks database (local hashmarks
and hashmarks sent from other peers). To quickly access
the hashmarks search you can press **Mod+Control+h**
(**Alt+Control+h** on Linux or **Command+Control+h**
on MacOS), or just click on the hashmarks library button
in the toolbar.

Your search query will be applied to the title, description,
comment or object path (so you can search for CIDs) of hashmarks.
The search is case-insensitive.

After typing a search query, run the search by pressing
**Shift + Return**.

Following IPNS keys
===================

There is basic support for following IPNS names/keys. When browsing
an IPNS path (e.g **/ipns/awesome.ipfs.io**), open the IPFS
menu on the left, and click on **Follow IPNS resource**).

The IPNS name or key will be periodically resolved (the resolve frequency
is configurable). The resolved entries are added as hashmarks inside
the IPNS feed and can be browsed from the hashmarks manager.
