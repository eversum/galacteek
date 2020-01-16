#!/bin/bash
#
# Credits: from the great https://github.com/Pext/Pext
#

set -x
set -e

# use RAM disk if possible
if [ -d /dev/shm ]; then
    TEMP_BASE=/dev/shm
else
    TEMP_BASE=/tmp
fi

BUILD_DIR=$(mktemp -d "$TEMP_BASE/galacteek-MacOS-build-XXXXXX")

cleanup () {
    if [ -d "$BUILD_DIR" ]; then
        rm -rf "$BUILD_DIR"
    fi
}

trap cleanup EXIT

OLD_CWD="$(pwd)"
VERSION=$(grep '__version__' galacteek/__init__.py|sed -e "s/__version__ = '\(.*\)'$/\1/")

COMMIT_SHORT=$(echo $TRAVIS_COMMIT|cut -c 1-8)

if [ "$TRAVIS_BRANCH" != "master" ]; then
    DMG_DEST="Galacteek-${COMMIT_SHORT}.dmg"
else
    DMG_DEST="Galacteek-${VERSION}.dmg"
fi

pushd "$BUILD_DIR"/

# install Miniconda
wget https://repo.continuum.io/miniconda/Miniconda3-4.6.14-MacOSX-x86_64.sh
bash Miniconda3-4.6.14-MacOSX-x86_64.sh -b -p ~/miniconda -f
rm Miniconda3-4.6.14-MacOSX-x86_64.sh

export PATH="$HOME/miniconda/bin:$PATH"

# create conda env
conda create -n galacteek python=3.7 --yes
source activate galacteek

# install dependencies
pip install -r "$OLD_CWD"/requirements.txt
pip install "$OLD_CWD"/dist/galacteek-${VERSION}-py3-none-any.whl

# leave conda env
source deactivate

# create .app Framework
mkdir -p galacteek.app/Contents/
mkdir galacteek.app/Contents/MacOS galacteek.app/Contents/Resources galacteek.app/Contents/Resources/galacteek
cp "$OLD_CWD"/travis/Info.plist galacteek.app/Contents/Info.plist

# copy Miniconda env
cp -R ~/miniconda/envs/galacteek/* galacteek.app/Contents/Resources/

# copy icons
mkdir -p galacteek.app/Contents/Resources/share/icons
cp "$OLD_CWD"/share/icons/galacteek.icns galacteek.app/Contents/Resources/share/icons

# copy go-ipfs
mkdir -p galacteek.app/Contents/Resources/bin
cp $HOME/bin/ipfs galacteek.app/Contents/Resources/bin

# Install libmagic (disabled for now, python-magic finds the library
# but raises an exception, still something to change here)
# brew install libmagic
# cp -av /usr/local/Cellar/libmagic/*/lib/* galacteek.app/Contents/Resources/lib

brew update

brew unlink python@2

# zbar install
brew install zbar
cp -av /usr/local/Cellar/zbar/*/lib/*.dylib galacteek.app/Contents/Resources/lib

# create entry script for galacteek
cat > galacteek.app/Contents/MacOS/galacteek <<\EAT
#!/usr/bin/env bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export PATH=$PATH:$DIR/../Resources/bin
$DIR/../Resources/bin/python $DIR/../Resources/bin/galacteek --from-dmg --no-ssl-verify
EAT

# create entry script for galacteek (debug)
cat > galacteek.app/Contents/MacOS/galacteek-debug <<\EAT
#!/usr/bin/env bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export PATH=$PATH:$DIR/../Resources/bin
$DIR/../Resources/bin/python $DIR/../Resources/bin/galacteek --from-dmg --no-ssl-verify -d
EAT

chmod a+x galacteek.app/Contents/MacOS/galacteek
chmod a+x galacteek.app/Contents/MacOS/galacteek-debug

# bloat deletion sequence
pushd galacteek.app/Contents/Resources
rm -rf pkgs
find . -type d -iname '__pycache__' -print0 | xargs -0 rm -r
rm -rf lib/python3.7/site-packages/Cryptodome/SelfTest/*
rm -rf lib/python3.7/site-packages/PyQt5/Qt/plugins/geoservices
rm -rf lib/python3.7/site-packages/PyQt5/Qt/plugins/sceneparsers
rm -rf lib/cmake/
rm -f bin/sqlite3*
rm -rf include/
rm -rf share/{info,man}
popd
popd

# Get the create-dmg repo
git clone https://github.com/andreyvit/create-dmg $HOME/create-dmg

# generate .dmg
$HOME/create-dmg/create-dmg --hdiutil-verbose --volname "galacteek-${VERSION}" \
    --volicon "${OLD_CWD}"/share/icons/galacteek.icns \
    --hide-extension galacteek.app $DMG_DEST "$BUILD_DIR"/
