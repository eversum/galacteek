.. _filemanager:

File manager
============

.. image:: ../../../../share/icons/folder-open.png
    :width: 64
    :height: 64

By clicking on the folder icon in the application's toolbar you'll get
access to the filemanager for importing content in your IPFS repository
through the *Mutable File System* (see :term:`MFS`).

*Note*: the filemanager is slow for rendering large directories, always
use the UnixFS explorer in that case (using right-click, *Explore* or
with *Ctrl-x*)

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

Chunker
^^^^^^^

From the *Chunker* menu you can choose the chunking algorithm.
It defines which strategy IPFS will use to break files into blocks:

- **Fixed size**: files are split into fixed-size blocks
- **Rabin**: fingerprinting chunker (you can specify a minimum, average
  and maximum block size)

Use raw blocks for leaf nodes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This option tells IPFS to use raw blocks for the leaf nodes in
the :term:`DAG`. When using this option, these nodes won't have
any UnixFS wrapper (it saves space in the repository, this is used
in the IPFS Wikipedia mirror for instance).

Use the filestore
^^^^^^^^^^^^^^^^^

If you've enabled the filestore on your local daemon and
want to use it when importing content from the filemanager,
check this option.

*Note*: the content that you've imported using the filestore will
only be available when this feature is enabled on the daemon.
Files imported in the filestore and linked in the MFS will
trigger *timeouts* (when listing the MFS path) if the filestore
feature is disabled on the daemon.

Store timestamp metadata
^^^^^^^^^^^^^^^^^^^^^^^^

This option is accessible from the timeframe selector widget
(click on the clock to open it).

This option controls how the files are linked inside the 
MFS. When time metadata is enabled, filenames are prefixed
with a timestamp and other metadata. Files are then grouped
by day, and you can later filter files by date.

*Note*: this option is disabled by default and persisted.

Selecting the working folder
----------------------------

The folder selector button lets you select the current working folder
in your filesystem (see :term:`MFS`).

Adding files in the *Encrypted files* folder will self-encrypt them with
your profile's RSA key (only you will be able to open them). When you open
an encrypted file it is first decrypted into an unpinned IPFS
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
dialog for directories only. This will recursively import the directory.
You can then choose if you want to import hidden files, and if you
want to enable the usage of *.gitignore* files (git ignore rules files)
if there's a *.gitignore* file in the selected directory.

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

File context menu
------------------

Right-clicking an entry in the file manager will popup a menu giving you a few
options:

- *Copy CID to the clipboard*
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

Searching
---------

You can search your files by typing a name or regular expression
pattern in the search box (all matching files will be selected in the
file manager tree).

Keyboard shortcuts
------------------

The following keyboard shortcuts are available within the files manager:

- **Mod + c** or **Mod + y**: Copy selected item's IPFS path to the clipboard
- **Mod + a**: Copy selected item's CID to the clipboard
- **Mod+x**: Explore item if it is a directory
