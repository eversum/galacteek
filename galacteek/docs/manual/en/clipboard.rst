
Using the clipboard
===================

*Note*: on Unix/Linux systems, the *selection* clipboard will always be
used as the primary clipboard, while on other platforms the system's
clipboard will be used.

The clipboard manager
---------------------

.. image:: ../../../../share/icons/clipboard.png
    :width: 64
    :height: 64

From the application's toolbar you can access the clipboard manager button.
It records the computer's clipboard activity and keeps an history of all the
IPFS CIDs or paths that have been stored in it since the application was
started.

It supports **drag and drop**, so drag-and-dropping a link to an IPFS
object on the clipboard manager button will register this object in the
history.

It is also possible to drag and drop local files and directories
(URLs with the file:// prefix) to the clipboard manager (from the browser,
file manager, or from another application). For files, their size has to
be inferior to 64Mb. There is no size limit for directories, so use with care.

Whenever the clipboard contains a new valid reference to an IPFS object, the
clipboard tracker gathers information about this object (performing an object
stat and determining its MIME type) and puts it on top of the clipboard stack,
making it the current item.

The current clipboard item in the stack is represented next to the clipboard
manager button. If available, an icon matching the discovered MIME type of
the IPFS object is set on the clipboard item button. Clicking on the clipboard
item button opens up a menu listing the different possible actions for this
object:

- **Open**: open the IPFS resource depending on the object type
- **Open with application**: open with custom application
- **Open with default system application**: open with the system's default
  application (it uses **xdg-open** on Linux or the **open** command on MacOS)
- **Hashmark**: hashmark this object
- **Pin**: recursively pin this object
- **Download**: download this object to the downloads folder
- **Set as homepage**
- **DAG view**
- **Run IPLD explorer**
- **Open with Markdown editor**

Supported formats
-----------------

The clipboard manager supports the following formats:

- *IPFS CID version 0*, for example
  **QmRifA98t769dzkDv2gQocqJPXGtTySR5dPkyTaUZXtkLo**
- *IPFS CID version 1 (base58-encoded)*, for example
  **zb2rhd4c97sLJwmnVvUjW5movikNJaYBMfpfpGP7hktYtt8Bo**
- *IPFS CID version 1 (base32-encoded)*, for example
  **bafkreic7mf6cvjyxbrabxkswgpel2ebcjfxj35zmmzgyi6cf35bz7mstgy**
- *IPFS path* for example
  **/ipfs/QmWzhNYvNaxz41qitbqMaTDbViFoES1NgTuoYC7dAAMJw3/src/tools** or 
  **/ipfs/QmdjTSAM2xSVsXcusNHRoES4KqkJ5mW17u6oQARTWMuWMF/CHANGES** or
  **/ipfs/bafkreic7mf6cvjyxbrabxkswgpel2ebcjfxj35zmmzgyi6cf35bz7mstgy**
- *IPNS path* for example **/ipns/ipfs.io** or
  **/ipns/Qmef8KSNLZZfdnrxHZKhCBBynSUFLQ4RrH88wW3sTWxfwB**
- *URLs using the fs: or dweb: scheme* for example
  **fs:/ipfs/QmRifA98t769dzkDv2gQocqJPXGtTySR5dPkyTaUZXtkLo** or
  **dweb:/ipfs/QmRifA98t769dzkDv2gQocqJPXGtTySR5dPkyTaUZXtkLo**
- *URLs using the ipfs:// or ipns:// scheme* for example
  **ipfs://bafybeigbtqkmsaeu6qcyp2oklp6qxjcq7twidewmx7h3ycokylhxk44ugy/** or
  **ipns://ipfs.io**
- *HTTP/HTTPs URLs that use an IPFS http gateway (like ipfs.io)* for example
  **https://ipfs.io/ipfs/QmRifA98t769dzkDv2gQocqJPXGtTySR5dPkyTaUZXtkLo** or
  **http://localhost:8080/ipns/peerpad.net**.

Keyboard shortcuts
------------------

*Mod* is the *Control* key on Linux and the *Command* key on MacOS X.

Each of these shortcuts will act on the current item in the clipboard
stack:

- **Mod+o** opens the IPFS resource corresponding to the current
  item
- **Mod+e** opens the explorer for the current clipboard item (only
  available if the resource is a directory)
- **Mod+g** opens the DAG viewer for the current clipboard item
- **Mod+i** opens the IPLD Explorer application for the current
  clipboard item
- **Mod+p** pins (recursively) the IPFS object
- **Mod+1** sets item number 1 in the stack as the current item
- **Mod+2** sets item number 2 in the stack as the current item
- **Mod+3** sets item number 3 in the stack as the current item
- **Mod+4** sets item number 4 in the stack as the current item
- **Mod+5** sets item number 5 in the stack as the current item
- **Mod+6** sets item number 6 in the stack as the current item
- **Mod+7** sets item number 7 in the stack as the current item
- **Mod+8** sets item number 8 in the stack as the current item
- **Mod+9** sets item number 9 in the stack as the current item
