# Agent skills setup proposal

Status: proposed. These sections show the exact setup text for review.
They do not change the repository's agent instructions yet.

## Append to AGENTS.md

```markdown
## Agent skills

### Issue tracker

Specs and tickets use GitHub Issues in `vimkim/html-serve`.
Read `docs/agents/issue-tracker.md` before tracker operations.

### Triage labels

Use the role mappings in `docs/agents/triage-labels.md`.

### Domain docs

This repository has one domain context.
Read `docs/agents/domain.md` before domain exploration or design.
```

## Create docs/agents/issue-tracker.md

```markdown
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
```

## Create docs/agents/triage-labels.md

```markdown
# Triage labels

Use these GitHub label strings for the five triage roles.

| Role | GitHub label | Meaning |
| --- | --- | --- |
| needs-triage | needs-triage | A maintainer must evaluate the issue |
| needs-info | needs-info | The reporter must supply more information |
| ready-for-agent | ready-for-agent | The issue has enough detail for agent implementation |
| ready-for-human | ready-for-human | The issue requires human implementation |
| wontfix | wontfix | The team will not implement the issue |
```

## Create docs/agents/domain.md

```markdown
# Domain documentation

This repository has one domain context.

1. Read `GLOSSARY.md` before domain exploration or design.
2. Read relevant documents in `docs/adr/` when that directory exists.
3. Use glossary terms consistently in documents, issues, and code.
4. Report conflicts between a proposed change and an accepted decision.

Proceed when the glossary or decision documents do not exist.
Create glossary entries when domain terms become settled.
Create an ADR only for a decision with a meaningful reversal cost and a documented trade-off.
```

## External setup state

The issue tracker choice is accepted. The default triage labels await approval.
Create missing labels only after approval and successful repository access.
This proposal does not authorize creating a remote repository or pushing source.
