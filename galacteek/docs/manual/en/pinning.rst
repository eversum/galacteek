
Pinning content
===============

.. image:: ../../../../share/icons/pin.png
    :width: 64
    :height: 64

The concept of pinning is a fundamental core feature of IPFS. By pinning an
object to your node, you start serving that content to the
network, increasing its availability and resilience.

Pinning manually in the browser
-------------------------------

Within a browsing tab, you can manually pin a page with the **PIN** tool button
at the far right, which allows single or recursive pinning.

- *Pin (single)* will pin only the IPFS object representing
  the current page
- *Pin (recursive)* will pin the IPFS object (current page, which
  can be a directory node) recursively
- *Pin parent (recursive)* will pin the parent of the current object
  recursively (can be useful if you are browsing a file and want to pin
  the parent directory recursively).
- *Pin page's links* will pin the IPFS objects referenced in the
  current page's HTML code

You will get a system tray notification when the pinning is complete.

Pinning IPFS links in a webpage
-------------------------------

If you are browsing a webpage which contains relative or absolute
IPFS links and you want to pin those objects, select *PIN page's links*
from the **PIN** button. This will scan IPFS links contained in the
current page and open a separate tab from which you can select single or
recursive pinning for each link found. Once confirmed, the selected
objects are queued for pinning.

Automatic pinning
-----------------

You can also activate the automatic pinning with the **Automatic PIN** switch
button. When it's activated, all pages visited in this browsing session will be
automatically pinned to your IPFS node.

In the application's toolbar, next to the clipboard manager,
another switch button activates application-wide automatic pinning.

Pinning status
--------------

In the status bar (at the bottom of the window), the pinning status icon gives
information about the status of the pinning queues. Clicking on it gives a view of
the objects being pinned.
