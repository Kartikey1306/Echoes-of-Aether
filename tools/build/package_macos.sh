#!/bin/zsh
# macOS release zip from an existing build (Builds/macOS/EchoesOfAether.app, made by EOA/Build/macOS): checks the
# app's ad-hoc signature, then zips it with README.txt into Builds/EchoesOfAether_macOS.zip ready to upload.
# The app is universal (Apple Silicon + Intel) but not notarized; README.txt explains the first-launch steps.
# Usage: tools/build/package_macos.sh
set -u
cd "$(dirname "$0")/../.."
ROOT=$PWD
APP=$ROOT/Builds/macOS/EchoesOfAether.app
ZIP=$ROOT/Builds/EchoesOfAether_macOS.zip
STAGE=$ROOT/Builds/.mac_stage

[ -d "$APP" ] || { echo "no build at $APP: run EOA/Build/macOS first"; exit 1; }
echo "== signature"
codesign --verify --deep --strict "$APP" || { echo "signature check failed"; exit 1; }
lipo -archs "$APP/Contents/MacOS/"*

echo "== packaging"
rm -rf "$STAGE" "$ZIP"
mkdir -p "$STAGE/EchoesOfAether"
cp -cR "$APP" "$STAGE/EchoesOfAether/"          # APFS clone: no extra disk space
cp tools/build/macos_README.txt "$STAGE/EchoesOfAether/README.txt"
ditto -c -k --sequesterRsrc --keepParent "$STAGE/EchoesOfAether" "$ZIP"
rm -rf "$STAGE"
ls -lh "$ZIP"
echo "== done"
