# Search, navigation, and recent visits

Status: design in progress. Work-tracker item: 391. Starting revision: `a3e3030`.

The reader needs to locate files and directories quickly, inspect search results, and return to previously visited paths.
The shared vocabulary is in [the glossary](../GLOSSARY.md).

## Agreed behavior

One finder screen has three modes. Each mode has a button on the directory listing.

| Button | Results | Preview | Open action |
| --- | --- | --- | --- |
| Find files | File paths that match a fuzzy query | File source with line numbers | Open the file with its existing viewer behavior |
| Find contents | Matching text, grouped by file | File source with the selected match highlighted | Open the selected file |
| Find directories | Directory paths that match a fuzzy query | Directory context where useful | Open the directory listing |

The finder matches relative paths, including parent directory names.
Arrow keys change the selection. Enter opens the selection. Escape closes the finder.
Selecting a result updates its preview without opening the result.
Closing the finder restores focus to its opening button.
On narrow screens, the preview appears below the results.

Search covers the serving root by default. A Current directory option limits search to the current directory and its descendants.
Search respects ignore rules and skips hidden entries by default.
An Include hidden and ignored option includes those entries. Search always excludes Git's `.git` internals.
This search filter does not change the ordinary directory listing.

Content queries use literal text by default.
Smart case ignores case unless the query contains uppercase characters.
A Regex toggle enables regular expressions.
Content search requires the `rg` executable.
If `rg` is missing, the finder explains that requirement. File finding, directory finding, and normal viewing remain available.

Go to root opens the serving root listing.
The Markdown toolbar uses Directory listing instead of Files.
That link retains its existing destination: the Markdown file's parent directory.

Recently visited contains files and directories ordered by their latest visit.
A repeated visit moves an existing entry to the top.
Previews, supporting assets, and background requests do not create visits.
History is separate from modification-time sorting.
History persists across server restarts and port changes, with separate histories for separate serving roots.
The server stores history under `$XDG_CACHE_HOME/html-serve/`, or `~/.cache/html-serve/` when that variable is absent.

Specs and implementation tickets belong in `vimkim/html-serve` GitHub Issues.
The configured remote returns HTTP 404 to the authenticated `vimkim` account.
Keep publication drafts local until that repository becomes accessible. Repository creation and pushing source require separate authorization.

## Proposed remaining behavior

These choices await the reader's answer:

- Include symlinked files in search only when their targets remain inside the serving root.
- Skip symlinked directories during recursive search.
- Preserve existing symlink behavior for ordinary direct-link browsing.

Implementation will use bounded previews, search results, and query execution.
The finder will show truncation, unavailable previews, invalid patterns, and search failures explicitly.
HTML and other active document source will appear as text in previews.

## Proposed verification boundaries

Approve these boundaries before implementation tests start:

| Boundary | What it verifies | Practical limit |
| --- | --- | --- |
| Live CLI and HTTP server | Search queries, root and scope rules, ignores, previews, missing rg, visit classification, persistence, and existing routing | Does not verify browser focus or interaction |
| Headless browser | Finder modes, selection, previews, keyboard navigation, root navigation, Markdown naming, recent visits, and narrow layouts | Does not prove behavior on every filesystem |
| Built wheel | Installed viewer, finder assets, vendor chunks, fonts, and license notices | Does not replace interaction tests |

Use the existing Python integration and Playwright boundaries.
Keep directory navigation and sorting functional without JavaScript.
Run `just test`, `just browser-test`, and `just build` before the final review.
Test the task worktree with temporary environments. Keep the installed editable command attached to the primary checkout.

## Proposed implementation slices

1. Navigation and naming: add Go to root and rename the Markdown Directory listing link.
2. File and directory finder: add the shared screen, fuzzy path matching, source previews, scope, and ignore controls.
3. Content finder: add rg queries, match selection, source highlighting, and clear dependency and query errors.
4. Recent visits: record deliberate navigation, persist history, and provide links to revisit files and directories.

Each slice includes its UI, server behavior where necessary, and focused verification.
The content finder depends on the shared finder. History can follow the finder without depending on its search implementation.
Commit task changes before requesting the approved local merge workflow.
