<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5
-->

Use [mkdoc.sh](./mkdoc.sh) to build and test documentation using MkDocs
  
  
  # After git clone run:
  ./scripts/mkdoc.sh setup

  # During docmentation development
  ./scripts/mkdoc.sh serve

  # Before commit
  ./scripts/mkdoc.sh build

Then GitHub CI/CD will automaticaly deploy new documentation to pages