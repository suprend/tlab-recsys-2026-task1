# Publication-only whitespace correction

15 октября 2026. Staged diff validation caught one extra blank line at EOF in the newly added full-export script. Unstaged diff validation had not inspected the untracked file; the commit stopped before approval or execution. Root explicitly authorized the publisher to remove only this blank line.

The accepted source SHA was `3a255515514d06d7e7e13970477cf67461033067aaf4b3a29d91ff49a9510d8d`; the published SHA is `59565643f58a3b34bb716c6cc071d7e1802d79aaf0b707e1537459b0a5377afa`. Byte comparison limits the change to terminal newline count, and parsed Python ASTs are identical. No semantic change, new test result, source execution or data acceptance is claimed. The [final independent review](tlab009-full-export-final-rereview.md) remains the semantic evidence for these bytes. Any subsequent execution proposal hashes the published script, never the stale prior proposal.
