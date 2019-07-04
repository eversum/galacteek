#!/bin/bash

set -x

IFS='' read -r -d '' UPLOADTOOL_BODY <<"EOF"
## galacteek release\n
\n
Download the AppImage (for Linux) or the DMG image (for macos)\n
from below.\n
\n
After downloading the AppImage, make it executable and then run it:\n
\n
> chmod +x Galacteek-0.4.8-x86_64.AppImage\n
./Galacteek-0.4.8-x86_64.AppImage\n
EOF

export UPLOADTOOL_BODY

if [ "$TRAVIS_OS_NAME" = "linux" ]; then
	bash upload.sh Galacteek*.AppImage
fi

if [ "$TRAVIS_OS_NAME" = "osx" ]; then
	bash upload.sh Galacteek*.dmg
fi
