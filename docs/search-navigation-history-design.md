# Search, navigation, and recent visits

Status: approved on 2026-10-16. Work-tracker item: 391. Starting revision: `a3e3030`.

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

The approved spec is [GitHub issue 1](https://github.com/vimkim/docserve/issues/1).
Its four implementation tickets are issues [2](https://github.com/vimkim/docserve/issues/2),
[3](https://github.com/vimkim/docserve/issues/3), [4](https://github.com/vimkim/docserve/issues/4),
and [5](https://github.com/vimkim/docserve/issues/5).
The repository became accessible during implementation. Its canonical name is now `vimkim/docserve`.
The previous `vimkim/html-serve` URL redirects there. Source pushes require separate authorization.

## Search boundary

- Include symlinked files in search only when their targets remain inside the serving root.
- Skip symlinked directories during recursive search.
- Preserve existing symlink behavior for ordinary direct-link browsing.

Implementation will use bounded previews, search results, and query execution.
The finder will show truncation, unavailable previews, invalid patterns, and search failures explicitly.
HTML and other active document source will appear as text in previews.

## Approved verification boundaries

| Boundary | What it verifies | Practical limit |
| --- | --- | --- |
| Live CLI and HTTP server | Search queries, root and scope rules, ignores, previews, missing rg, visit classification, persistence, and existing routing | Does not verify browser focus or interaction |
| Headless browser | Finder modes, selection, previews, keyboard navigation, root navigation, Markdown naming, recent visits, and narrow layouts | Does not prove behavior on every filesystem |
| Built wheel | Installed viewer, finder assets, vendor chunks, fonts, and license notices | Does not replace interaction tests |

Use the existing Python integration and Playwright boundaries.
Keep directory navigation and sorting functional without JavaScript.
Run `just test`, `just browser-test`, and `just build` before the final review.
Test the task worktree with temporary environments. Keep the installed editable command attached to the primary checkout.

## Approved implementation slices

1. Navigation and naming: add Go to root and rename the Markdown Directory listing link.
2. File and directory finder: add the shared screen, fuzzy path matching, source previews, scope, and ignore controls.
3. Content finder: add rg queries, match selection, source highlighting, and clear dependency and query errors.
4. Recent visits: record deliberate navigation, persist history, and provide links to revisit files and directories.

Each slice includes its UI, server behavior where necessary, and focused verification.
The content finder depends on the shared finder. History can follow the finder without depending on its search implementation.
Commit task changes before requesting the approved local merge workflow.


## Verification result

Code revision: `8bdb14b`. Local integration awaits approval.

- `just test`: 47 Python tests passed.
- `just browser-test`: 16 headless-browser tests passed.
- `just build`: wheel and source distribution passed.
- Installed wheel: 13 finder/history HTTP tests and three finder browser scenarios passed.
- Wheel inventory: viewer files, finder files, vendor chunks, fonts, and third-party notices are present.
- Every vendor file matches its SHA-256 manifest entry.
- Markdown source validation and `git diff --check` passed.

A narrow-screen finder screenshot received a visual review.
Tests use isolated caches and temporary environments. The installed editable command still follows the primary checkout.

## Standards

The initial review found three issues: Git-internal symlink aliases, truncated UTF-8 previews, and unusual Linux filenames.
A follow-up found one issue with unsaved visits after cache write failures.
Regression tests cover all four findings. Commits `e359879` and `34eb5b8` resolve them.
The final response-header adjustment also passed review.

Final result: no remaining material Standards or correctness findings.

## Spec

The initial review found three issues: ignore-source priority, Git-internal symlink aliases, and preview line numbering.
Commit `e359879` resolves all three. The reviewer reran each reproduction successfully.

Final result: no remaining Spec findings or additional scope creep.

Review totals: Standards, zero open findings. Spec, zero open findings. Neither axis has an unresolved issue.

## Integration state

The primary checkout advanced to `7f9ff88` during this work.
That commit reorganizes the English and Korean documentation.
Preserve that documentation during the approved rebase. Place detailed finder documentation in the command reference after integration.
Later main commits rename the command to docserve with CLI aliases and add request paths to HTTP error logs.
Preserve those changes during integration as well.

The task checkout is separate from the primary checkout. No local merge, installation sync, or source push occurred.
