# docserve guide

[English overview](../README.md) · [한국어 소개](../README.ko.md)

This guide contains the command reference and development details.
See the [development-only security notice](../README.md#docserve) before serving files.

Run `docserve` in an SSH terminal from the directory you want to serve:

```sh
docserve
docserve .
docserve '/another/output directory'
docserve path/to/review.html
docserve README.md
docserve -d '/another/output directory' -f review.html
docserve --port 8080
```

Installation adds `docserve`, `html-serve`, and `md-serve` to PATH. All three
commands use the same server and accept the same arguments. The aliases support
both HTML and Markdown.

Directory URLs always show a listing, even when `index.html` or `index.htm` exists. Click
the filename to open that page, or select it explicitly on the command line.

## Directory listing

Listings show clickable **Title**, **Created**, and **Modified** column headers.
Select a header to sort by that column; select it again to reverse direction.
Title starts A–Z; either date starts newest first. An arrow marks the active
column and direction. The initial order is Modified, newest first. There are
no separate sorting buttons.

Title sorts by filename, including its extension, using Unicode
case-insensitive character order with case-sensitive ties. Digits sort as
characters (`report10` before `report2`). Date ties sort alphabetically, and
unavailable dates stay last in either direction. Files and directories share
the order, with `../` always first when inside the serving root.

Sorting works without JavaScript and is recorded in the directory URL:
`?sort=title`, `?sort=created`, or `?sort=modified`. Add `&order=asc` or
`&order=desc` to choose direction; a missing or invalid direction uses that
column's initial direction. Parent and child directory links retain both
settings. A bare directory URL starts newest modification first. File links
retain their normal URLs; browser Back returns to the sorted listing, while
the Markdown **Directory listing** link opens its parent listing in default order.

Dates use the server's local timezone; hover over a date for its ISO timestamp
and UTC offset. Directory dates describe the directory itself, not its newest
descendant. Symlink dates follow the target while the visible name retains `@`;
dangling links remain listed with unavailable dates.

**Created** means the filesystem object's birth date, which can change when
files are copied or checked out. It is **Unavailable** when the filesystem
does not supply it. On Linux, optional GNU Coreutils `stat` supplies birth dates
in bounded batches; missing tools, unsupported filesystems, or lookup timeouts
leave the listing usable. Metadata-change time is never substituted for birth
time. Add `--verbose` to see lookup diagnostics.

## Finding and revisiting paths

The directory listing has **Find files**, **Find contents**, **Find directories**,
and **Recently visited** buttons. Each opens the same finder screen.
**Go to root** opens the serving root listing. This is the directory selected
by the CLI, which can be the enclosing Git repository root.

File and directory queries use fuzzy matching against relative paths.
For example, `docsrev` can match `docs/design-review.md`.
Click a result to select it and preview its source on the right.
Use the arrow keys to select another result. Press Enter or click **Open file**
or **Open directory** to navigate. Escape closes the finder and returns focus
to its button. The preview appears below the results on narrow screens.

Search covers the serving root by default. Select **Current directory** to
search the current directory and its descendants. Search reads `.gitignore`,
`.ignore`, and `.rgignore` files within the serving root. Hidden and ignored
entries stay out of results unless **Include hidden and ignored** is selected.
Git's `.git` internals always stay excluded. These filters do not change the
ordinary directory listing. Empty directories are searchable.
Search skips symlinked directories and symlinked files whose targets leave
the serving root. Ordinary direct links retain their existing behavior.

**Find contents** requires the `rg` (ripgrep) executable on the server.
The finder explains when it is unavailable. File and directory finding and
normal viewing still work without it. Content queries use literal text and
smart case: lowercase queries ignore case, while queries with uppercase
characters are case-sensitive. Select **Regex** for regular expressions.
Results include matching line numbers, and the preview highlights the selected
match. Opening a result uses its normal viewer, including rendered Markdown.

Use **Include filenames (regex)** to search only matching filenames and
**Exclude filenames (regex)** to skip matching filenames. Both are optional
and match the filename, including its extension, rather than directory names.
For example, include `\.md$` for Markdown files or `\.(md|txt)$` for Markdown
and text files; exclude `^draft` to skip names starting with `draft`.
These filters always use ripgrep regular expressions, independently of the
content **Regex** checkbox, and use the same smart-case behavior. Exclusion
takes precedence. Invalid patterns show an error. Filename filtering shares
the content search's execution budget.

Search returns up to 200 results after scanning at most 20,000 entries.
Tree scans and content searches each have a three-second execution budget.
Content search skips files larger than 2 MiB and returns up to 40 matching
lines per file. The finder reports limited results, skipped large files,
and invalid patterns. Narrow the query or scope when results are limited.
Previews show UTF-8 source as text, including HTML, without executing it.
They read at most 2 MiB and display at most 200 lines and 64 KiB around the
selected line. Binary files retain their normal open or download action.

**Recently visited** contains the latest 100 distinct files and directories
opened through browser navigation. Revisiting a path moves it to the top.
Previews, scripts, images, background requests, and HEAD requests do not add
visits. Removed paths disappear from results. Type to filter the history.
Visit order is separate from the listing's modification-time order.
Choose **All** (the default), **Files only**, or **Directories only** to filter
the history by entry type. The text query and entry-type filter work together
and preserve visit order; filtering keeps the stored history intact.

The server stores each serving root's history in a separate file under
`$XDG_CACHE_HOME/html-serve/visits/`, normally `~/.cache/html-serve/visits/`.
History survives restarts, port changes, and changes between LAN and VPN
addresses. Servers for the same root share the history. It stores paths,
entry types, and visit times, without file contents. If the cache is
unavailable, the server keeps recent visits in memory for its current session.

## Paths and file selection

| Arguments | Serving directory | Printed links |
| --- | --- | --- |
| None | Current directory | Directory listing at `/` |
| `DIR` (including `.`) | Directory's Git repository root, or `DIR` outside Git | Root listing and the selected directory listing |
| `PATH/FILE` | File's Git repository root, or parent directory outside Git | Root listing and the selected file |
| `-d DIR` or `--directory DIR` | `DIR` | Directory listing at `/` |
| `-f FILE` or `--file FILE` | Current directory | Root listing and `FILE` relative to the current directory |
| `DIR -f FILE` | `DIR` | Root listing and `FILE` relative to `DIR` |
| `-d DIR -f FILE` | `DIR` | Root listing and `FILE` relative to `DIR` |

A positional path can be relative or absolute; quoted `~` paths are expanded.
It must name an existing directory or regular file. Any regular file can be
selected: HTML opens as a page, Markdown uses the preview, and other formats
use the browser's normal behavior. Selecting a positional directory or file
serves its enclosing Git repository root, so links and assets elsewhere in the
repository remain accessible. Detection starts from the selected directory or
the file's directory, regardless of your current directory. Nested repositories
and linked worktrees use their own roots.
Outside a repository, or if Git is unavailable or detection fails, the selected
directory or the file's parent directory is served instead. With no path argument,
the current directory is served without Git discovery.

`--directory` (`-d`) requires a directory. `--file` (`-f`) requires a file path
relative to the selected serving directory; absolute paths and `..` components
are rejected. Use a positional file path to select a file outside the current
directory, or choose its serving root explicitly with `-d`.

A positional path together with `-d` is an error. A positional file together
with `-f` is also an error. A positional directory can be combined with `-f`.
For example, from a repository root, `docserve docs -f nested/review.html`
serves `docs` and prints a link to `/nested/review.html`;
`docserve docs/nested/review.html` serves the repository root and prints a
link to `/docs/nested/review.html` alongside the root listing link.
`docserve docs/nested` serves the repository root and also prints a link to
`/docs/nested/`. Outside Git, selecting the file serves `docs/nested` and links to
`/review.html` alongside `/`. To explicitly serve only the file's parent
directory, use `docserve docs/nested -f review.html`.

## Markdown preview

Click any `.md` or `.markdown` file in the directory listing to read it as a
rendered page. Direct links and links from other documents also render by
default, including uppercase extensions. A URL such as `/docs/design.md` stays
at that address; no preview option or generated `.html` file is needed.
`docserve --file README.md` prints links directly to the preview.

The viewer supports GitHub Flavored Markdown tables, task lists, strikethrough,
heading anchors, and these document features:

````markdown
```mermaid
flowchart LR
    Markdown --> Preview
```

![Architecture](./figures/architecture.svg)
![Remote SVG](https://example.com/architecture.svg)

Inline math: $E = mc^2$

$$
\int_0^1 x^2\,dx = \frac{1}{3}
$$
````

Relative image and document links resolve from the Markdown file's original
directory. Keep referenced files within the directory being served. SVGs are
displayed as images. LaTeX equations use KaTeX's supported math syntax; ordinary
code blocks and inline code remain literal. Invalid diagrams or equations show
their source and error while the remaining document stays readable.

The toolbar has **Directory listing** and **Raw** links. Add `?raw=1` to a Markdown URL to
read the original source as UTF-8 plain text. Preview requires JavaScript in a
modern browser. It starts in **light mode**, including when the operating
system prefers dark. Use the toolbar's **Dark mode** toggle to switch either
way; the chosen theme also updates Mermaid diagrams. The browser remembers the
choice for the same scheme, host, and port. A different LAN/VPN address or port
can start light again. If browser storage is unavailable, the toggle still
works for the current page. Explicit colors inside images and diagram source
remain controlled by their authors. Document HTML
is sanitized; Mermaid uses its strict security setting and KaTeX disables
trusted commands.

Renderer scripts, styles, diagram modules, and math fonts are bundled locally.
Once installed, serving needs no GitHub request, CDN, Node/npm, or additional
Python packages. Remote images still require access to their host. Markdown
rendering happens in the browser; HTTP clients receive the viewer HTML at the
default URL and can request `?raw=1` for the document source. The internal URL
prefix `/__serve_html__/` is reserved for viewer assets.

## Server options

The `serve-html` agent skill can also suggest a command after creating an HTML
file. Run that command yourself in an SSH terminal:

```bash
docserve --bind 0.0.0.0 --directory '/absolute/path/to/output' --file 'review.html'
```

The CLI starts a foreground HTTP server, chooses a memorable free port, and
prints plain URLs for the server's active Tailscale/VPN and LAN IPv4
addresses. Open a printed URL from your PC, then press Ctrl+C in the SSH terminal
to stop the server. The port stays bound throughout serving; concurrent runs get
different ports. The directory includes adjacent CSS, JavaScript, and images.

The **Root directory** section prints a plain root URL for each address, followed
by a short network label such as Tailscale or LAN. When a selected directory or
file has a different URL, **Selected path** prints its direct URL for every
address too. Directory links end in `/`; spaces, Unicode, and special characters
are URL-encoded. A selection that is already the root uses the root URLs without
duplicates. The output needs no Markdown renderer, and terminals that recognize
URLs can make them clickable.

Successful HTTP requests are quiet by default. Startup links and errors remain
visible; each HTTP error includes the request method and URL, for example
`code 404, message File not found — "GET /favicon.ico HTTP/1.1"`.
Add `--verbose` to print all request logs.

With no `--port`, or with `--port 0`, the CLI tries these patterns in order:

| Priority | Pattern | Examples |
| --- | --- | --- |
| 1 | Four identical digits | `7777`, `8888`, `9999`, `5555`, `4444`, `3333`, `2222`, `1111` (in this order) |
| 2 | Adjacent repeated pairs | `1122`, `2233`, `3322`, `7788` |
| 3 | Three repeats next to an adjacent digit | `1112`, `2223`, `2333`, `7778` |
| 4 | Ascending or descending sequences | `1234`, `5678`, `8765`, `9876` |
| 5 | Other repeated pairs | `2255`, `5577`, `8800` |
| 6 | Alternating pairs | `1212`, `4545`, `8080`, `9090` |
| 7 | Mirrored pairs | `1221`, `3443`, `8008`, `9009` |
| 8 | Round thousands | `7000`, `8000`, `9000` |
| 9 | Round hundreds | `2500`, `8100` |

Within each pattern after the first, lower port numbers come first. Occupied
or permission-denied ports are skipped. Automatic selection excludes the
four-digit ports in the [Fetch port-blocking list](https://fetch.spec.whatwg.org/#port-blocking),
including `6666`, which browsers block for HTTP. After the memorable patterns,
the CLI tries the remaining allowed ports from `1024` to `9999`, then asks the
kernel for an available port if every four-digit choice is unavailable. Each
attempt binds the actual server and retains the successful socket.

`--port PORT` with a nonzero value requires that exact port; an occupied port
fails before any links are printed. `--interface NAME` limits the printed links,
while `--bind ADDRESS` controls which IPv4 address accepts connections. A
loopback bind prints only a local link. Python 3 and Linux `ip` (iproute2) are
required for network discovery.
The CLI never opens a browser. Reachability from a PC depends on its network
route to the server.

## Source and installation

Clone this repository to `~/gh/docserve` and run `just sync` from its main
checkout. The recipe installs `docserve` and its `html-serve` and `md-serve` aliases
in `~/.local/bin` as an editable uv tool. It requires uv and just.
Serving requires Python 3.10+ and Linux `ip` for network discovery. It has no third-party Python runtime dependencies.

The server lives in `src/html_serve/cli.py`; viewer files and their bundled
dependencies live in `src/html_serve/assets/` and ship in the Python package.
`tools/serve-html-assets/` owns their npm lockfile and reproducible build.
`just assets` rebuilds the committed vendor files. Node/npm are only needed for
development and browser tests. Python and browser checks run with `just test`
and `just browser-test`; `just build` creates wheel and source distributions.

The dotfiles repository owns fresh-machine bootstrap, `daily-update`, and old
script/asset path compatibility. The `vimkim/my-skills` collection owns agent
instructions. See [migration details](migration.md).

The editable command follows edits in the primary checkout. Keep task worktrees
separate, and test them in temporary environments before merging. `just sync`
requires the primary checkout on main.

## Verification

```bash
just test
```

The tests exercise the CLI's live HTTP lifecycle, preferred port ordering,
occupied preferred ports, automatic fallback and reservation,
concurrent servers, occupied fixed ports, Ctrl+C shutdown, encoded HTML paths,
adjacent assets, and interface discovery. They also verify directory listings
with index pages present, explicit index links, directory redirects, positional
directories and files, root and direct links on each network, Git root discovery
for nested repositories and linked worktrees, parent-directory fallback,
explicit directory overrides, short and
long options, and conflicting arguments. CLI integration uses temporary files
and a deterministic `ip` fixture. No deployed
files are used. They also cover Markdown routing, raw responses, GET/HEAD,
SVG content types, asset paths, and rendering with `--verbose`. Listing checks
cover all three columns in both directions, date ties and unavailable dates,
header links and navigation, nanosecond modification ordering, alphabetical mode,
special filenames, symlink dates, birth-date availability, partial lookup
results, batching, argument-size fallback, and lookup deadlines.

Headless Chromium verification exercises actual clicks from the directory
listing, direct encoded URLs, relative Markdown links and SVG images, a remote
SVG image from a second local HTTP origin, Mermaid, LaTeX math, heading IDs,
sanitization, errors within individual blocks, light and dark mobile layouts,
saved themes, denied storage, early theme selection during slow loading,
rapid toggles during Mermaid loading, directory sorting without JavaScript,
and existing HTML behavior. Network requests outside localhost are blocked in
the main rendering scenario, and a plain document verifies lazy loading:

```sh
npm --prefix tools/serve-html-assets ci
# Install a headless test browser if it is not cached already.
cd tools/serve-html-assets
npx playwright install chromium --only-shell
npm test
```

To check an installed wheel, set `HTML_SERVE_TEST_SCRIPT` to its installed
`html_serve/cli.py` when running either suite. `HTML_SERVE_TEST_PYTHON` selects
the browser fixture's Python interpreter. These overrides do not replace the
globally installed command.

Set `SERVE_HTML_CHROMIUM_EXECUTABLE` to use an existing Chromium binary.
Set `SERVE_HTML_SCREENSHOT` to an absolute PNG path to capture the rendered
fixture. All browser launches in the test are headless.

## Updating bundled assets

The build dependencies are pinned in `tools/serve-html-assets/package-lock.json`.
Node 22.12 or later and npm are needed only to rebuild the committed assets or
run browser tests:

```sh
npm --prefix tools/serve-html-assets ci
npm --prefix tools/serve-html-assets run build
```

The build creates the `vendor/` directory, includes third-party license texts,
and records package versions and file SHA-256 hashes in `vendor/manifest.json`.
Commit the regenerated files together with dependency changes. The source
viewer HTML, CSS, and JavaScript live outside `vendor/` and can be edited
directly. `theme.js` applies the saved preference before stylesheets load.
The build scopes the pinned light-only and dark-only GitHub Markdown styles
into one stylesheet so theme changes need no additional download. Build tools
and test dependencies are excluded from the runtime wheel.
