<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: LicenseRef-FPGA-Verification-Commercial-Reciprocity-1.0
-->

### The documentation is currently under development and does not reflect the project's current status!
### It will be updated in upcoming versions.

Use [mkdoc.sh](./mkdoc.sh) to build and validate the documentation with MkDocs.

```bash
# After cloning the repository
./docs/mkdoc.sh setup

# During documentation development
./docs/mkdoc.sh serve

# Before committing
./docs/mkdoc.sh build
```

GitHub Actions builds the documentation in strict mode and deploys changes from
`main` to GitHub Pages.
