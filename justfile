# Install only from the primary main checkout so the command has a stable source.
sync:
    @test -d .git || { echo "Run just sync from the primary checkout." >&2; exit 1; }
    @test "$(git branch --show-current)" = main || { echo "Run just sync from main." >&2; exit 1; }
    @if uv tool list | awk '$1 == "html-serve" { found = 1 } END { exit !found }'; then uv tool uninstall html-serve; fi
    uv tool install --editable . --reinstall

test:
    uv run python -B -m unittest discover -s tests -v

browser-test:
    npm --prefix tools/serve-html-assets ci --no-audit --no-fund
    npm --prefix tools/serve-html-assets test

assets:
    npm --prefix tools/serve-html-assets ci --no-audit --no-fund
    npm --prefix tools/serve-html-assets run build

build:
    uv build

check: test build
