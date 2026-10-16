# Extraction provenance and compatibility

Imported from vimkim/dotfiles commit 5076e96 on 2026-10-16. Earlier history
remains in that repository. The server, viewer, vendored browser dependencies,
asset builder, Python tests, browser tests, and design notes moved together.

Dotfiles owns bootstrap and daily-update integration, forwarding launchers at
`~/.config/my-scripts/bin/html-serve` and `serve-html.py`, and a compatibility
symlink from `~/.config/my-scripts/share/serve-html` to this package's assets.
The Markdown skill validator still uses that asset path. On migration, matching
legacy assets are backed up to `~/.local/state/html-serve/legacy-assets` before
chezmoi applies the symlink. Modified legacy assets remain in place and are
reported for review. The new server always uses its packaged assets.

Local setup does not create or publish a GitHub repository. Until separately
published, a fresh machine cannot clone vimkim/html-serve and daily-update skips
this checkout when it has no published upstream.
