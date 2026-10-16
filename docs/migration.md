# Extraction provenance and compatibility

Imported from vimkim/dotfiles commit 5076e96 on 2026-10-16. Earlier history
remains in that repository. The server, viewer, vendored browser dependencies,
asset builder, Python tests, browser tests, and design notes moved together.

Dotfiles owns bootstrap and daily-update integration, forwarding launchers at
`~/.config/my-scripts/bin/html-serve` and `serve-html.py`, and a compatibility
symlink from `~/.config/my-scripts/share/serve-html` to this package's assets.
The Markdown skill validator still uses that asset path. On migration, matching
legacy assets are backed up to `~/.local/state/html-serve/legacy-assets` before
chezmoi applies the symlink. Direct bootstrap invocation clears only the old
directory's state record after verifying and backing up its contents. This
preparation runs outside a parent chezmoi apply, which holds the state lock. Modified legacy assets remain in place and are
reported for review. The new server always uses its packaged assets.

## Rename to docserve

The project and Python distribution now use the name `docserve`. The repository is
`vimkim/docserve`. Installation provides three equivalent commands: `docserve`,
`html-serve`, and `md-serve`. Both aliases support every document format and option.

The Python import package stays `html_serve`, so existing imports and deployed
asset symlinks remain valid. The `/__serve_html__/` asset prefix, saved-theme key,
and test environment variables also retain their legacy names for compatibility.
Existing checkouts can keep their `html-serve` directory name. New installations
use `~/gh/docserve`. Run `just sync` from the primary checkout on `main`.
The recipe removes an installed legacy `html-serve` uv tool before installing
`docserve`. Removing the old tool first prevents its uninstaller from deleting
the new package's `html-serve` alias. Repeating `just sync` reinstalls all three
commands under the `docserve` package.

The development-only security notice in both READMEs describes Git-root discovery,
network exposure, and the lack of authentication or TLS. This rename does not
change the server's access controls.
