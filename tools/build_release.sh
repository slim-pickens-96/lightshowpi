#!/bin/bash
#
# Build a release tarball of the committed tree:
#   dist/lightshowpi-<VERSION>.tar.gz  and  dist/lightshowpi-<VERSION>.tar.gz.sha256
#
# Only committed files are included (git archive), so local overrides.cfg,
# .venv, logs, caches and test output never end up in a release.
#
# Usage:  tools/build_release.sh [git-ref]      (default: HEAD)
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
REF="${1:-HEAD}"
VERSION="$(git show "${REF}:VERSION" | tr -d '[:space:]')"
NAME="lightshowpi-${VERSION}"

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "WARNING: you have uncommitted changes; they are NOT included in the release." >&2
fi

mkdir -p dist
git archive --format=tar.gz --prefix="${NAME}/" -o "dist/${NAME}.tar.gz" "${REF}"
(cd dist && sha256sum "${NAME}.tar.gz" > "${NAME}.tar.gz.sha256")

echo "Built dist/${NAME}.tar.gz"
cat "dist/${NAME}.tar.gz.sha256"
