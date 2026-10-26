#!/usr/bin/env bash

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

# Write the pins of an environment: for every application enabled in
# deploy/<environment>/inventory/group_vars/all/apps.yml, the git tag of its
# last multicz release (<component>-vX.Y.Z). An application that has no tag
# yet is left unpinned and is deployed from website_repo_version.
#
#   uv run --no-sync scripts/deploy-pins.sh production

set -euo pipefail

environment="${1:?usage: deploy-pins.sh <environment>}"
dir="deploy/${environment}/inventory/group_vars/all"

apps=$(python - "${dir}/apps.yml" <<'PY'
import sys

import yaml

data = yaml.safe_load(open(sys.argv[1])) or {}
print("\n".join(data.get("website_apps_enabled") or []))
PY
)

pins=""
for app in ${apps}; do
    # Catalog keys use underscores, multicz components use dashes.
    component="${app//_/-}"
    version=$(multicz get "${component}")
    tag="${component}-v${version}"
    if git rev-parse --quiet --verify "refs/tags/${tag}" >/dev/null; then
        pins+="  ${app}: ${tag}"$'\n'
    else
        echo "no release tag ${tag}: ${app} stays unpinned" >&2
    fi
done

{
    echo "# SPDX-License-Identifier: MIT"
    echo "# Copyright (c) 2026 Chris <goabonga@pm.me>"
    echo
    echo "---"
    echo "# Release of each deployed application, written by the deploy-plan workflow"
    echo "# (scripts/deploy-pins.sh) from the multicz tags. Do not edit by hand."
    if [ -z "${pins}" ]; then
        echo "website_apps_pins: {}"
    else
        echo "website_apps_pins:"
        printf '%s' "${pins}"
    fi
} > "${dir}/pins.yml"
