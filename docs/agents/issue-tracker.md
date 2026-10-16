# Issue tracker: GitHub

Specs and tickets belong in GitHub Issues for `vimkim/html-serve`.
Use `gh` with an explicit `--repo vimkim/html-serve` argument.

- Read issues with `gh issue view NUMBER --json number,title,body,labels,comments`.
- List issues with `gh issue list --state open --json number,title,body,labels`.
- Write multiline issue text to a temporary file.
- Create issues with `gh issue create --title TITLE --body-file FILE`.
- Apply the configured triage labels with `gh issue edit NUMBER --add-label LABEL`.
- Use native sub-issues and dependency links when available.
- Otherwise, include Parent and Blocked by references in issue bodies.

PRs as a request surface: no.

The repository returned HTTP 404 during initial setup on 2026-10-16.
Keep publication drafts in repository documentation until GitHub access succeeds.
Report publication failures explicitly.
Repository creation and source pushes require separate user authorization.
