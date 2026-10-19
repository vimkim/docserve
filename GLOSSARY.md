# docserve

docserve lets a reader browse a served directory tree and open its documents.

## Language

**Serving root**:
The directory at the top of the tree exposed by one running html-serve server.
_Avoid_: Filesystem root, repository root (unless it is also the serving root)

**Allowed root**:
An additional directory explicitly exposed with `--allow-root DIR` so absolute
filesystem links into it can open. It has its own document URLs, finder scope,
and visit history; the serving root remains the main directory at `/`.

**Directory listing**:
The page that shows the immediate files and subdirectories of a served directory.
_Avoid_: Files (as the navigation label for this page)

**Finder**:
A screen for finding files or directories, matching file contents, and selecting recently visited or updated paths within the served tree.

**Preview**:
A view of a selected search result's file contents before the reader opens that result.

**Visit**:
A reader opening a file or directory listing. Selecting a preview or loading a supporting asset is not a visit.

**Recently visited**:
Files and directories ordered by the reader's most recent visit to each one.
_Avoid_: Recently modified (which describes changes to file contents or directory entries)

**Recently updated**:
Files ordered by their latest modification time, regardless of whether the reader has visited them.
