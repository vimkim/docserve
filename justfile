# Install or refresh a regular tool from the primary main checkout.
sync:
    @test -d .git || { echo "Run just sync from the primary checkout." >&2; exit 1; }
    @test "$(git branch --show-current)" = main || { echo "Run just sync from main." >&2; exit 1; }
    uv tool install --reinstall .

# Explicit optional checker setup; never downloads during a check.
checker-setup:
    @test -d .git || { echo "Run just checker-setup from the primary checkout." >&2; exit 1; }
    @test "$(git branch --show-current)" = main || { echo "Run just checker-setup from main." >&2; exit 1; }
    uv tool install --reinstall '.[check]'
    "$(uv tool dir)/docserve/bin/playwright" install chromium --only-shell

test:
    uv run python -B -m unittest discover -s tests -v

# Install Chromium explicitly first: uv run --extra check playwright install chromium --only-shell
checker-test:
    uv run --extra check python -B -m unittest discover -s tests -p test_mermaid_check.py -v

browser-test:
    npm --prefix tools/serve-html-assets ci --no-audit --no-fund
    npm --prefix tools/serve-html-assets test

assets:
    npm --prefix tools/serve-html-assets ci --no-audit --no-fund
    npm --prefix tools/serve-html-assets run build

build:
    uv build

check: test build
