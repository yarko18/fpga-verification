<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

Use [docs.sh](./docs.sh) to build and test documentation using MkDocs
  
  
  # After git clone run:
  ./scripts/docs.sh setup

  # During docmentation development
  ./scripts/docs.sh serve

  # Before commit
  ./scripts/docs.sh build

Then GitHub CI/CD will automaticaly deploy new documentation to pages