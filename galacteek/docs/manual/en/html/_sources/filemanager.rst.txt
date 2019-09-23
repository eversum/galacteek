
File manager
============

.. image:: ../../../../share/icons/folder-open.png
    :width: 64
    :height: 64

By clicking on the folder icon in the application's toolbar you'll get
access to the filemanager for importing content in your IPFS repository
through the *Mutable File System* (see :term:`MFS`).

Settings
--------

.. image:: ../../../../share/icons/settings.png
    :width: 64
    :height: 64

DAG generation format
^^^^^^^^^^^^^^^^^^^^^

You can choose between the *Balanced* DAG format (the default in IPFS)
or the *Trickle* format. This option has an impact on how
:term:`IPFS` will generate the :term:`DAG` structure for the files
that you import.

Importing some content with the *Trickle* format will generate
different CIDs compared to when the same content is being
imported with the default *Balanced* format becauses of the
differences in the DAG's structure (even though the
files data is the same).

You might want to use the *Trickle* DAG format for large files
(for instance video files), making DAG traversal potentially faster.

Use raw blocks for leaf nodes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This option tells IPFS to use raw blocks for the leaf nodes in
the :term:`DAG`. When using this option, these nodes won't have
any UnixFS wrapper (it saves space in the repository, this is used
in the IPFS Wikipedia mirror for instance).

Selecting the working folder
----------------------------

The folder selector button lets you select the current working folder
in your filesystem (see :term:`MFS`).

The *Temporary* and *Encrypted files* folders are by default in *offline*
mode.

Adding files in the *Encrypted files* folder will self-encrypt them with
your profile's RSA key (only you will be able to open them). When you open
an encrypted file it is first decrypted into an (unpinned, unannounced) IPFS
file object which will later on be garbage-collected by the daemon.

Importing your files using the files selection dialogs
------------------------------------------------------

.. image:: ../../../../share/icons/add-file.png
    :width: 64
    :height: 64

If you click on the **Add files** icon you are prompted with a file selection
dialog. All files selected will be imported to your IPFS repository. By default
your files will be wrapped with a directory in order to preserve filenames (you
can change this in the settings).

.. image:: ../../../../share/icons/add-folder.png
    :width: 64
    :height: 64

If you click on the **Add directory** icon you are prompted with a selection
dialog for directories only. This will recursively import the directory,
including dotfiles (files and directories starting with *.* on Linux)

Because the application accesses IPFS in an *asynchronous* manner, importing
even large amounts of data should not cause the application to hang or becoming
unresponsive so you can perform other tasks meanwhile, but the file manager
will prevent you from adding more content while the import is running.

Importing your files using the local file manager (drag-and-drop)
-----------------------------------------------------------------

.. image:: ../../../../share/icons/file-manager.png
    :width: 64
    :height: 64

Clicking on the file manager icon will open up a file manager displaying your
local files. Just select and drag-and-drop your files from the local file
manager to the IPFS file manager on the left and they will be imported to your
repository. Multiple selection is supported by holding the *Control* or *Shift*
keys.

Drag-and-dropping content from other applications is supported as well.

Offline mode
------------

The *Offline mode* button, when toggled, sets the filemanager in offline
mode for the current folder (it is a per-folder switch). In this mode,
adding new files to your node will not trigger an
announcement on the :term:`DHT` (meaning that other nodes will have no knowledge
yet that your node provides these files).

Later on, if you want to manually announce to the network that you provide
some files, right-click a file or directory and select
**Announce (DHT provide)** (for a directory, use the recursive version to
recursively announce the entire graph).

File context menu
------------------

Right-clicking an entry in the file manager will popup a menu giving you a few
options:

- *Copy multihash to the clipboard*
- *Copy full path to the clipboard*
- *Announce (DHT provide)*: announce to the network that you provide this
  file/directory
- *Announce (DHT provide, recursive)*: announce to the network that you provide this
  file/directory (recursively announces the whole graph)
- *Hashmark*: hashmark this item
- *Browse*: open a browser tab for this item
- *Open*: open this item with the resource opener
- *Explore*: for directories, open an explorer tab for this entry
- *Edit*: open this file in the text editor
- *Unlink*: this will dereference the item but not delete it (i.e. the
  content will still be available through your IPFS node)
- *Delete*: purge from your IPFS node (**note**: if others have *pinned* this
  data on their node, it will still be available)
- *Publish to IPNS key*: this will link this file to the given IPNS key

Keyboard shortcuts
------------------

The following keyboard shortcuts are available within the files manager:

- **Mod + c** or **Mod + y**: Copy selected item's IPFS path to the clipboard
- **Mod + a**: Copy selected item's multihash (CID) to the clipboard
- **Mod+x**: Explore item if it is a directory
