from PyQt5.QtCore import QCoreApplication


def qtr(ctx, msg):
    return QCoreApplication.translate(ctx, msg)


# Main window messages


def iNoStatus():
    return QCoreApplication.translate('GalacteekWindow', 'No status')


def iGeneralError(msg):
    return QCoreApplication.translate('GalacteekWindow',
                                      'General error: {0}').format(msg)


def iErrNoCx():
    return QCoreApplication.translate(
        'GalacteekWindow',
        'No connection available')


def iCxButNoPeers(id, agent):
    return QCoreApplication.translate(
        'GalacteekWindow',
        'IPFS ({1}): not connected to any peers').format(
        id, agent)


def iConnectStatus(id, agent, peerscount):
    return QCoreApplication.translate(
        'GalacteekWindow',
        'IPFS ({1}): connected to {2} peer(s)').format(
        id, agent, peerscount)


def iItemsInPinningQueue(items):
    return QCoreApplication.translate(
        'GalacteekWindow',
        'Items in pinning queue: {}'.format(items))


def iHelp():
    return QCoreApplication.translate('GalacteekWindow', 'Help')


def iUnknown():
    return QCoreApplication.translate('GalacteekWindow', 'Unknown')


def iUnknownAgent():
    return QCoreApplication.translate('GalacteekWindow', 'Unknown agent')


def iMinimized():
    return QCoreApplication.translate(
        'GalacteekWindow',
        'galacteek was minimized to the system tray')


# Headers used in the various tree widgets
def iPath():
    return QCoreApplication.translate('IPFSTreeView', 'Path')


def iCidOrPath():
    return QCoreApplication.translate('IPFSTreeView', 'CID or path')


def iFileName():
    return QCoreApplication.translate('IPFSTreeView', 'Name')


def iFileSize():
    return QCoreApplication.translate('IPFSTreeView', 'Size')


def iFileHash():
    return QCoreApplication.translate('IPFSTreeView', 'Hash')


def iMultihash():
    return QCoreApplication.translate('IPFSTreeView', 'Multihash')


def iMimeType():
    return QCoreApplication.translate('IPFSTreeView', 'Mime type')


def iPinSuccess(path):
    return QCoreApplication.translate(
        'GalacteekWindow',
        '{0} was pinned successfully').format(path)


def iPinError(path, errmsg):
    return QCoreApplication.translate(
        'GalacteekWindow',
        'Error pinning {0}: {1}').format(path, errmsg)


def iManual():
    return QCoreApplication.translate('GalacteekWindow', 'Manual')


def iHashmark():
    return QCoreApplication.translate('GalacteekWindow', 'Hashmark')


def iHashmarkThisPage():
    return QCoreApplication.translate('GalacteekWindow', 'Hashmark this page')


def iHashmarks():
    return QCoreApplication.translate('GalacteekWindow', 'Hashmarks')


def iLocalHashmarks():
    return QCoreApplication.translate('GalacteekWindow', 'Local hashmarks')


def iSharedHashmarks():
    return QCoreApplication.translate('GalacteekWindow', 'Shared hashmarks')


def iHashmarksLibraryCountAvailable(count):
    return QCoreApplication.translate(
        'GalacteekWindow',
        'Hashmarks library: {0} hashmarks available'
    ).format(count)


def iFileManager():
    return QCoreApplication.translate('GalacteekWindow', 'File Manager')


def iTextEditor():
    return QCoreApplication.translate('GalacteekWindow', 'Editor')


def iHashmarksManager():
    return QCoreApplication.translate('GalacteekWindow', 'Hashmarks manager')


def iKeys():
    return QCoreApplication.translate('GalacteekWindow', 'IPFS Keys')


def iSettings():
    return QCoreApplication.translate('GalacteekWindow', 'Settings')


def iPinningStatus():
    return QCoreApplication.translate('GalacteekWindow', 'Pinning status')


def iEventLog():
    return QCoreApplication.translate('GalacteekWindow', 'Event Log')


def iPeers():
    return QCoreApplication.translate('GalacteekWindow', 'Peers')


def iIpfsSearchText(text):
    return QCoreApplication.translate('GalacteekWindow',
                                      'Search: {0}').format(text)


def iIpfsSearch():
    return QCoreApplication.translate('GalacteekWindow',
                                      'Search')


def iNewProfile():
    return QCoreApplication.translate('GalacteekWindow', 'New Profile')


def iSwitchedProfile():
    return QCoreApplication.translate('GalacteekWindow',
                                      'Successfully switched profile')


def iDagViewer():
    return QCoreApplication.translate('GalacteekWindow', 'DAG viewer')


def iLocalHashmarksCount(count):
    return QCoreApplication.translate(
        'GalacteekWindow',
        'Local hashmarks: {0} hashmarks available'
    ).format(count)


def iOpen():
    return QCoreApplication.translate('GalacteekWindow', 'Open')


def iDownload():
    return QCoreApplication.translate('GalacteekWindow', 'Download')


def iCancel():
    return QCoreApplication.translate('GalacteekWindow', 'Cancel')


def iMediaPlayer():
    return QCoreApplication.translate('GalacteekWindow', 'Media Player')


def iChat():
    return QCoreApplication.translate('GalacteekWindow', 'Chat')


def iLangEnglish():
    return QCoreApplication.translate('Galacteek', 'English')


def iLangFrench():
    return QCoreApplication.translate('Galacteek', 'French')


def iYes():
    return QCoreApplication.translate('Galacteek', 'yes')


def iNo():
    return QCoreApplication.translate('Galacteek', 'no')


def iDelete():
    return QCoreApplication.translate('Galacteek', 'Delete')


def iRemove():
    return QCoreApplication.translate('Galacteek', 'Remove')


def iInvalidInput():
    return QCoreApplication.translate('Galacteek', 'Invalid input')


def iCannotResolve(objPath):
    return QCoreApplication.translate(
        'Galacteek',
        'Cannot resolve object: <b>{}</b>').format(objPath)


def iKey():
    return QCoreApplication.translate('Galacteek', 'Key')


def iValue():
    return QCoreApplication.translate('Galacteek', 'Value')


def iMerkleLink():
    return QCoreApplication.translate('Galacteek', 'Merkle link')


def iIpfsInfos():
    return QCoreApplication.translate('GalacteekWindow', 'IPFS informations')


def iIpfsQrCodes():
    return QCoreApplication.translate('GalacteekWindow', 'IPFS QR codes')


def iIpfsQrEncode():
    return QCoreApplication.translate('GalacteekWindow', 'QR encoding')


def iNoTitle():
    return QCoreApplication.translate('GalacteekWindow', 'No title')


def iNoTitleProvided():
    return QCoreApplication.translate('GalacteekWindow',
                                      'Please specify a title')


def iFinished():
    return QCoreApplication.translate('GalacteekWindow', 'Finished')


def iPinned():
    return QCoreApplication.translate('GalacteekWindow', 'Pinned')


def iPinning():
    return QCoreApplication.translate('GalacteekWindow', 'Pinning')


def iPin():
    return QCoreApplication.translate('GalacteekWindow', 'Pin')


def iPinSingle():
    return QCoreApplication.translate('GalacteekWindow', 'Pin (single)')


def iPinRecursive():
    return QCoreApplication.translate('GalacteekWindow', 'Pin (recursive)')


def iPinRecursiveParent():
    return QCoreApplication.translate('GalacteekWindow',
                                      'Pin parent (recursive)')


def iPinPageLinks():
    return QCoreApplication.translate('GalacteekWindow', "Pin page's links")


def iBatchPin():
    return QCoreApplication.translate('GalacteekWindow', 'Batch pin')


def iDoNotPin():
    return QCoreApplication.translate('GalacteekWindow', 'Do not pin')


def iGlobalAutoPinning():
    return QCoreApplication.translate('GalacteekWindow',
                                      'Global automatic pinning')


def iZoomIn():
    return QCoreApplication.translate('GalacteekWindow', 'Zoom in')


def iZoomOut():
    return QCoreApplication.translate('GalacteekWindow', 'Zoom out')


def iQuit():
    return QCoreApplication.translate('GalacteekWindow', 'Quit')


def iRestart():
    return QCoreApplication.translate('GalacteekWindow', 'Restart')


def iClearHistory():
    return QCoreApplication.translate('GalacteekWindow', 'Clear history')


def iAtomFeeds():
    return QCoreApplication.translate('GalacteekWindow', 'Atom feeds')


# IPFS daemon ui messages

def iFsRepoMigrateNotFound():
    return QCoreApplication.translate(
        'Galacteek',
        'Warning: could not find IPFS repository migration tool')


def iGoIpfsNotFound():
    return QCoreApplication.translate(
        'Galacteek',
        'Error: Could not find go-ipfs on your system')


def iGoIpfsTooOld():
    return QCoreApplication.translate(
        'Galacteek',
        'Error: go-ipfs version found on your system is too old')


def iGoIpfsFetchAsk():
    return QCoreApplication.translate(
        'Galacteek',
        'go-ipfs was not found on your system: download '
        'binary from IPFS distributions website (https://dist.ipfs.io) ?')


def iGoIpfsFetchTimeout():
    return QCoreApplication.translate(
        'Galacteek',
        'Timeout while fetching go-ipfs distribution')


def iGoIpfsFetchSuccess():
    return QCoreApplication.translate(
        'Galacteek',
        'go-ipfs was installed successfully')


def iGoIpfsFetchError():
    return QCoreApplication.translate(
        'Galacteek',
        'Error while fetching go-ipfs distribution')


def iNewReleaseAvailable():
    return QCoreApplication.translate(
        'Galacteek',
        'New release available: upgrade with pip install -U galacteek')


# MFS

def iMusic():
    return QCoreApplication.translate('FileManagerForm', 'Music')


def iPictures():
    return QCoreApplication.translate('FileManagerForm', 'Pictures')


def iImages():
    return QCoreApplication.translate('FileManagerForm', 'Images')


def iTemporaryFiles():
    return QCoreApplication.translate('FileManagerForm', 'Temporary')


def iEncryptedFiles():
    return QCoreApplication.translate('FileManagerForm', 'Encrypted files')


def iVideos():
    return QCoreApplication.translate('FileManagerForm', 'Videos')


def iHome():
    return QCoreApplication.translate('FileManagerForm', 'Home')


def iCode():
    return QCoreApplication.translate('FileManagerForm', 'Code')


def iDocuments():
    return QCoreApplication.translate('FileManagerForm', 'Documents')


def iWebPages():
    return QCoreApplication.translate('FileManagerForm', 'Web Pages')


def iDWebApps():
    return QCoreApplication.translate('FileManagerForm', 'Dapps')


def iQrCodes():
    return QCoreApplication.translate('FileManagerForm', 'QR codes')
