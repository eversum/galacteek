#!/bin/bash

set -x
set -e

GO_IPFS_VERSION=0.4.23
FS_MIGRATE_VERSION=1.5.1

PIP=pip3
PYTHONEX=python3

mkdir -p $HOME/bin

# Fetch and untar go-ipfs
if [ "$TRAVIS_OS_NAME" = "linux" ]; then
	PYTHONEX=python3.7
	wget https://dist.ipfs.io/go-ipfs/v${GO_IPFS_VERSION}/go-ipfs_v${GO_IPFS_VERSION}_linux-amd64.tar.gz
	tar -C $HOME -xzvf go-ipfs_v${GO_IPFS_VERSION}_linux-amd64.tar.gz

	wget https://dist.ipfs.io/fs-repo-migrations/v${FS_MIGRATE_VERSION}/fs-repo-migrations_v${FS_MIGRATE_VERSION}_linux-amd64.tar.gz
	tar -C $HOME -xzvf fs-repo-migrations_v${FS_MIGRATE_VERSION}_linux-amd64.tar.gz

	wget https://github.com/wasmerio/wasmer/releases/download/0.12.0/wasmer-linux-amd64.tar.gz
	tar -C $HOME -xzvf wasmer-linux-amd64.tar.gz

	export DISPLAY=":99.0"
	/sbin/start-stop-daemon --start --quiet --pidfile /tmp/custom_xvfb_99.pid --make-pidfile --background --exec /usr/bin/Xvfb -- :99 -screen 0 1920x1200x24 -ac +extension GLX +render -noreset
	sleep 3
	herbstluftwm &
	sleep 1
fi

if [ "$TRAVIS_OS_NAME" = "osx" ]; then
	wget https://dist.ipfs.io/go-ipfs/v${GO_IPFS_VERSION}/go-ipfs_v${GO_IPFS_VERSION}_darwin-amd64.tar.gz
	tar -C $HOME -xzvf go-ipfs_v${GO_IPFS_VERSION}_darwin-amd64.tar.gz

	wget https://dist.ipfs.io/fs-repo-migrations/v${FS_MIGRATE_VERSION}/fs-repo-migrations_v${FS_MIGRATE_VERSION}_darwin-amd64.tar.gz
	tar -C $HOME -xzvf fs-repo-migrations_v${FS_MIGRATE_VERSION}_darwin-amd64.tar.gz
fi

mv $HOME/go-ipfs/ipfs $HOME/bin
mv $HOME/fs-repo-migrations/fs-repo-migrations $HOME/bin

$HOME/bin/ipfs init

export PYTHONPATH=$PYTHONPATH:/usr/local/lib/python3.7/dist-packages
export PATH=$PATH:$HOME/bin

$PYTHONEX -m venv venvg
source venvg/bin/activate

$PIP install -r requirements.txt
$PIP install -r requirements-dev.txt

$PYTHONEX setup.py build install
$PYTHONEX setup.py sdist bdist_wheel
