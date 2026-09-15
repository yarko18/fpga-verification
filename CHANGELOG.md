<!--
Copyright 2026 Yaroslav Mariukha
SPDX-License-Identifier: RPL-1.5

Unless explicitly acquired and licensed from Licensor under another license,
the contents of this file are subject to the Reciprocal Public License ("RPL")
Version 1.5, or subsequent versions as allowed by the RPL, and You may not copy
or use this file in either source code or executable form, except in compliance
with the terms and conditions of the RPL.

All software distributed under the RPL is provided strictly on an "AS IS"
basis, WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESS OR IMPLIED, AND LICENSOR
HEREBY DISCLAIMS ALL SUCH WARRANTIES, INCLUDING WITHOUT LIMITATION, ANY
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, QUIET
ENJOYMENT, OR NON-INFRINGEMENT. See the RPL for specific language governing
rights and limitations under the RPL.
-->

# Changelog

## 1.0.3 - 2026-09-15

- Added an optional default frame size to `ImageGenerator`.
- Expanded the simulation runner documentation and corrected the `run_rtl_test()` example.

## 1.0.2 - 2026-09-11

- Added the MkDocs Material documentation site, structured guides, and local
  documentation build helpers.
- Added automated documentation publication and restricted that workflow to
  relevant main-branch and pull-request changes.
- Replaced the former long-form README with a concise project entry point.

## 1.0.1 - 2026-09-10

- Preserved non-UTF-8 bytes while applying simulator-model source fixes.
- Pinned the tested cocotb and pyuvm versions and allowed the installed
  cocotbext-avalon package to provide its own compatible release.
- Restricted release CI to tags and added concurrency cancellation for
  superseded runs.
