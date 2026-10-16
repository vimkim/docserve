# docserve

Read README.md for the overview and security notice. Read docs/guide.md for
command behavior. The Python server and committed browser assets form one
installable package. Node/npm build the assets and run headless browser tests.
Keep the runtime independent of Node/npm and CDNs.

For server or asset changes, run `just test`, `just browser-test`, and `just build`.
Verify that the built wheel includes viewer files, vendor chunks, fonts, and
third-party notices. Regenerate vendor assets with `just assets` when changing
browser dependencies. Retain the manifest and license notices.

Run `just sync` from the primary main checkout after an approved local merge.
The editable installation follows that checkout. Use temporary environments to
test task worktrees without replacing the installed command.
