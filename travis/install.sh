#!/bin/bash

set -x
set -e

PIP=pip3
PYTHONEX=python3
SOLIDITY_VERSION=0.5.0

mkdir -p $HOME/bin

if [ "$TRAVIS_OS_NAME" = "linux" ]; then
	PYTHONEX=python3.6
	wget https://dist.ipfs.io/go-ipfs/v0.4.21/go-ipfs_v0.4.21_linux-amd64.tar.gz
	tar -C $HOME -xzvf go-ipfs_v0.4.21_linux-amd64.tar.gz

	export DISPLAY=":99.0"
	/sbin/start-stop-daemon --start --quiet --pidfile /tmp/custom_xvfb_99.pid --make-pidfile --background --exec /usr/bin/Xvfb -- :99 -screen 0 1920x1200x24 -ac +extension GLX +render -noreset
	sleep 3
	herbstluftwm &
	sleep 1
fi

if [ "$TRAVIS_OS_NAME" = "osx" ]; then
	wget https://dist.ipfs.io/go-ipfs/v0.4.21/go-ipfs_v0.4.21_darwin-amd64.tar.gz
	tar -C $HOME -xzvf go-ipfs_v0.4.21_darwin-amd64.tar.gz
fi

mv $HOME/go-ipfs/ipfs $HOME/bin

export PYTHONPATH=$PYTHONPATH:/usr/local/lib/python3.6/dist-packages
export PATH=$PATH:$HOME/bin

$PYTHONEX -m venv venvg
source venvg/bin/activate

$PIP install -r requirements.txt
$PIP install -r requirements-dev.txt

if [ "$TRAVIS_OS_NAME" = "osx" ]; then
	wget -O $HOME/bin/solc \
		"https://github.com/ethereum/solidity/releases/download/v0.5.10/solc-static-linux"
fi

$PYTHONEX setup.py build install
$PYTHONEX setup.py sdist bdist_wheel
