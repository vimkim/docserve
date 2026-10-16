# docserve

**English** · [한국어](README.ko.md) · [Command reference](docs/guide.md)

> AI writes the docs. Get back to reading them.

Open HTML and Markdown from your SSH server with one command. Get a memorable
free port, links for your network, and the surrounding files to explore.

![An SSH terminal runs docserve docs/review.md, then a browser displays the document alongside links to nearby files.](docs/assets/readme-workflow.svg)

> [!WARNING]
> **Development use only. Do not use docserve for production serving.**
> Passing a file or directory can expose its entire Git repository, including hidden or sensitive files.
> Symbolic links can expose files outside the serving directory.
> The server binds to all IPv4 interfaces by default and has no authentication or TLS.
> Anyone who can reach the server may read the served files. Use only on trusted development networks.
> Use `-d` to choose a dedicated output directory, or `--bind 127.0.0.1` with an SSH tunnel for local access.

## Why I built this

AI agents kept creating documents I actually wanted to read: explanations,
design notes, plans, and diagrams in Markdown and HTML.

But most of my work happens on a remote SSH server. Every new document meant
finding the file, starting a server, choosing a port, and figuring out which
address to open. Across different sessions and projects, that small chore kept
coming back.

My workflow was already a loop: **create a document → serve it → read it → repeat.**
I wanted a small command and a simple agent skill to make that loop easy.

So I built `docserve`. In my setup, the skill gives me a command after the
agent creates a document. I run it in the SSH terminal, open the printed link
on my computer, and read.

## Give it a file. Keep the context.

```sh
docserve docs/review.md
```

Example links with Tailscale available. Your address and free port will vary:

```text
Root directory:
- http://100.64.0.12:7777/ — Tailscale

Selected path:
- http://100.64.0.12:7777/docs/review.md — Tailscale
```

Open the document directly, or use the root listing to browse nearby files.
Keep the command running while you read. Press **Ctrl+C** when you finish.
Your computer needs a network route to the printed address, such as a shared
LAN or VPN.

The useful part is what you can leave to the command:

- **A port you can remember.** It tries free ports such as `7777`, `8888`, and
  `9999`, skips occupied ports, and keeps the chosen port reserved. Concurrent
  sessions get different ports.
- **The project around the file.** Pass a file or directory, and it detects the
  enclosing Git repository root. Browse related notes and keep relative links
  and assets accessible. Outside Git, it uses the directory or the file's parent.
- **Addresses you can use.** It detects active Tailscale, VPN, and LAN IPv4
  addresses and prints links to both the root and your selected document.
- **Documents ready to read.** HTML opens as HTML. Markdown renders with tables,
  Mermaid diagrams, math, SVG images, and a light/dark toggle. The renderer and
  fonts ship with the tool, so the preview needs no CDN.

Nearby files appear in a directory listing, with clickable **Title**,
**Created**, and **Modified** headers. Open another document from there without
returning to the terminal.

HTML and Markdown open with a slim banner. **Directory listing** opens a file
pane, and **Compact view** switches to floating controls with their own directory
popup. **Open standalone** opens the document in a separate tab.
See [document navigation](docs/guide.md#document-navigation).

Use **Find files**, **Find contents**, and **Find directories** to search paths
or text with rendered Markdown and HTML previews. **Go to root** returns to the serving root.
**Recently visited** keeps files and directories available across server restarts.
**Recently updated** finds changed documents recursively, newest first, with an
editable filename filter that starts with `.html` and `.md` files.
See [finding and revisiting paths](docs/guide.md#finding-and-revisiting-paths).
Run `docserve-recent .` for the same Recently updated search in your
terminal, or add `--json` for scripts. See the [command reference](docs/guide.md#recently-updated-files-from-the-terminal).

## Read from your phone, too

**Your agent writes it on the server. You read it on your phone.** Use a mobile
SSH terminal, or follow your [herdr](https://herdr.dev/) sessions through
[herdr-web-ui](https://github.com/devswha/herdr-web-ui). Run
`docserve docs/review.md` in a shell on the server, then tap a printed URL to
open the rendered document in your phone's browser.

Links have extra spacing for easier tapping. In terminals that support OSC 8
hyperlinks, each link keeps its full destination even when a long filename
wraps across the screen. Your phone needs a route to the server, such as the
same LAN or Tailscale/VPN.

## Start on your SSH server

Install [uv](https://docs.astral.sh/uv/) and
[just](https://github.com/casey/just), then run:

```sh
git clone https://github.com/vimkim/docserve.git ~/gh/docserve
cd ~/gh/docserve
just sync
```

`just sync` automatically installs **`docserve`**, **`html-serve`**, and
**`md-serve`**. All three commands accept the same arguments and serve both HTML
and Markdown. Existing `html-serve` commands keep working.

Serving requires **Python 3.10+** and Linux **iproute2** (`ip`). The Python
runtime has no third-party dependencies. Node/npm are for development only.

For automated Mermaid validation, install optional checker support with
`just checker-setup`, then run `docserve-check mermaid document.md --render --json`.
It uses the shipped viewer in headless Chromium. Omit `--render` for a syntax
check. See [setup, exit codes, and guarantees](docs/guide.md#mermaid-checks).

```sh
docserve                     # Browse the current directory
docserve docs/review.md      # Read Markdown, with its Git project as the root
docserve output/report.html  # Open HTML with its surrounding assets
```

Run the command in your SSH terminal, then open a printed URL in your computer's
browser. The command stays in the foreground. In my workflow, an agent skill
suggests the command. You can also run it directly.

## Read more

The detailed documentation lives in [`docs/`](docs/guide.md):

- [Paths, Git roots, and directory browsing](docs/guide.md#paths-and-file-selection)
- [Markdown, Mermaid, math, and themes](docs/guide.md#markdown-preview)
- [Ports, network addresses, and server options](docs/guide.md#server-options)
- [Development, tests, and bundled assets](docs/guide.md#source-and-installation)
