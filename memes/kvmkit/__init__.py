# Generated from _lib/kvmkit/__init__.py by _utils/sync-kvmkit.py. Edit the master copy.
"""kvmkit: shared building blocks for NanoKVM Go Apps.

The master copy lives in `_lib/kvmkit/` at the repository root. Each App
that uses it carries its own copy in `<app>/kvmkit/` so it stays a
self-contained ZIP. Edit the master copy, then run:

    python3 _utils/sync-kvmkit.py

Modules: screen (visible area, rounded corners, Layout), pager (pagination
with header and footer), text (8x8 font helpers), theme (colours), env
(setting parsers) and net (mDNS for `.local` names).
"""

VERSION = "0.1.0"
