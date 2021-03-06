# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The changelog for versions prior to v0.4.39 is not available, due to
the changes in the CHANGELOG formatting.

## [Unreleased]

## [0.4.41] - 2020-12-04
### Added
- Tor support
  - Tor proxying on all platforms (enabled manually from the
    status bar for now, very soon there'll be finer control
    of the relays via [stem](https://stem.torproject.org/))
  - Proxying of ipfs-search and cyber requests via Tor

- Add a new *anonymous* web profile
- Automatically fetch favicons when hashmarking an http(s) website
- Handle SSL certificate errors

- New python dependencies
  - [aiohttp-socks](https://pypi.org/project/aiohttp-socks/) >=0.5.5
  - validators >= 0.18.1

### Changed
- Browser tab UI
  - Use a block-style cursor for the address bar
  - Typing an .eth domain name automatically loads it through *ens://*
  - Run IPFS searches or searches with popular engines (duckduckgo, ..)
    from the address bar
  - Change the history lookup interface

- The @Earth workspace is now the first/default workspace in the WS stack
- Workspace APIs
  - Changed wsRegisterTab(): accept a *position* argument to insert tabs
    at the end of the tabs list or after the current tab

### Fixed
- Bookmarking of clearnet URLs

## [0.4.40] - 2020-11-29
### Added
- Lightweight BT client integration (asyncio-based)
  - Add torrents from .torrent files, magnet links
  - Automatically transform magnet links stored in the clipboard 
    to .torrent files stored in IPFS
  - Torrent to IPFS transfer: from the BT client you can easily
    transfer completed downloads to IPFS and have them linked in
    your *downloads* MFS directory.

- New python dependencies
  - [colour](https://github.com/vaab/colour) >= 0.1.5
  - [magnet2torrent](https://github.com/JohnDoee/magnet2torrent) >= 1.1.1

### Changed
- Log to time-rotated log files by default (use --log-stderr if you
  want logs to be sent to stderr instead)
- Per-module color styling of log records
- IPFS daemon init dialog
  - Add a combo box to select the IPFS content routing mode
  - Add a *Quit* button

## [0.4.39] - 2020-11-15
### Added
- Support for Windows (packaged as a one-file EXE and NSIS installer)

- Continuous Integration with Github Actions (Travis CI is still supported)
  - CI workflow for ubuntu (Bionic), MacOS and windows
  - Automatically embed CHANGELOG contents in GH releases

### Changed
- Move from quamash to [asyncqt](https://github.com/gmarull/asyncqt) (v 0.8.0)

### Fixed
- Fix issues with libmagic and zbar on Windows
- Fix issues with IPFS paths not always treated as POSIX paths
- Fix [#31](https://github.com/pinnaculum/galacteek/issues/31) (thanks @teknomunk)
- Fix [#32](https://github.com/pinnaculum/galacteek/issues/32) (thanks @teknomunk)
