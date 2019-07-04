#!/bin/bash

set -x

if [ "$TRAVIS_OS_NAME" = "linux" ]; then
	cd AppImage
	bash upload.sh Galacteek*.AppImage
fi

if [ "$TRAVIS_OS_NAME" = "osx" ]; then
	bash upload.sh Galacteek*.dmg
fi
