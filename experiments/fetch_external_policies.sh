#!/usr/bin/env bash
# Fetch the external XACML policies (XPA repository, fixed commit) into ./external/xpa
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HERE/external/xpa"; TMP="$(mktemp -d)"
COMMIT=89c000495d81a1a82ca8de2ab0fc73fecfc4e440
git clone -q https://github.com/dianxiangxu/XPA.git "$TMP/XPA"
git -C "$TMP/XPA" checkout -q "$COMMIT"
mkdir -p "$DEST"
for d in itrust3 pluto3 conference3 fedora-rule3 gpms; do
  mkdir -p "$DEST/$d"; cp "$TMP/XPA/Experiments/$d/$d.xml" "$DEST/$d/"
done
rm -rf "$TMP"
echo "external policies in $DEST"
