#!/usr/bin/env bash

# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

# Install the Draw.io CLI required by the MkDocs Draw.io hook on Debian CI.

set -euo pipefail

drawio_version="${DRAWIO_VERSION:-31.3.2}"
drawio_sha256="${DRAWIO_SHA256:-725453f32ef7f2f63f8b50b374857a5c312e2aaabcf221cb0600332741ae1094}"

if [[ "$(dpkg --print-architecture)" != "amd64" ]]; then
    printf 'Draw.io CI installation currently supports only amd64.\n' >&2
    exit 1
fi

run_apt() {
    if [[ "$(id -u)" -eq 0 ]]; then
        DEBIAN_FRONTEND=noninteractive apt-get "$@"
    else
        sudo env DEBIAN_FRONTEND=noninteractive apt-get "$@"
    fi
}

package_path="$(mktemp --suffix=.deb)"
trap 'rm -f "${package_path}"' EXIT

run_apt update
if apt-cache show libasound2t64 >/dev/null 2>&1; then
    alsa_package='libasound2t64'
else
    alsa_package='libasound2'
fi
run_apt install --yes --no-install-recommends \
    ca-certificates curl "${alsa_package}" xauth xvfb

curl --fail --location --silent --show-error \
    --output "${package_path}" \
    "https://github.com/jgraph/drawio-desktop/releases/download/v${drawio_version}/drawio-amd64-${drawio_version}.deb"
printf '%s  %s\n' "${drawio_sha256}" "${package_path}" | sha256sum --check -

run_apt install --yes --no-install-recommends "${package_path}"
