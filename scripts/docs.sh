#!/usr/bin/env bash

# Copyright 2026 Yaroslav Mariukha
# SPDX-License-Identifier: RPL-1.5

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd -- "${script_dir}/.." && pwd)"
python_command="${FPGA_DOCS_PYTHON:-python3.12}"

cd "${project_dir}"

case "${1:-help}" in
    setup)
        "${python_command}" -m pip install -e ".[docs]"
        ;;
    serve)
        "${python_command}" -m mkdocs serve
        ;;
    build)
        "${python_command}" -m mkdocs build --strict
        ;;
    help|-h|--help)
        printf '%s\n' \
            "Usage: scripts/docs.sh <command>" \
            "" \
            "Commands:" \
            "  setup  Install the documentation dependencies" \
            "  serve  Start the local documentation server" \
            "  build  Build and strictly validate the documentation"
        ;;
    *)
        printf 'Unknown command: %s\n' "$1" >&2
        printf 'Run scripts/docs.sh help for usage.\n' >&2
        exit 2
        ;;
esac
