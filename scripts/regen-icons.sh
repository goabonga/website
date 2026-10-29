#!/usr/bin/env bash

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

# Regenerate every derived branding asset from the canonical SVG at
# `assets/website.svg`. Re-run after editing the master SVG and commit the
# outputs: the docs workflow builds the site from the checked-in files and never
# runs this script.
#
# Outputs:
#   docs/website.svg   site logo   (zensical `[project.theme].logo`)
#   docs/favicon.ico   site icon   (zensical `[project.theme].favicon`)
#
# The favicon conversion needs cairosvg and Pillow, which are installed for this
# call only so that the native cairo stack stays out of the workspace.

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SRC="$ROOT/assets/website.svg"

if [[ ! -f "$SRC" ]]; then
  echo "regen-icons: missing $SRC" >&2
  exit 1
fi

# Zensical resolves theme assets relative to the docs dir, so the master SVG is
# copied rather than referenced across directories.
cp "$SRC" "$ROOT/docs/website.svg"

uv run --no-project --with cairosvg --with pillow python "$ROOT/scripts/generate_favicon.py" \
  -i "$ROOT/docs/website.svg" \
  -o "$ROOT/docs/favicon.ico"

echo "regen-icons: docs/website.svg + docs/favicon.ico from $SRC"
