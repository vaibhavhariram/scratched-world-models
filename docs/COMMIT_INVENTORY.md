# Commit inventory

P0 item 1/2 triage. Measured 2026-09-16, before any branch was pushed. Values only; each section
names the command that produced it.

## Branches

```
git for-each-ref --format='%(refname:short)' refs/heads/    # then rev-list / rev-parse per branch
```

| branch | commits | remote | state |
|---|---|---|---|
| `main` | 1 | `origin/main` | 1 behind — local is stale, remote has a commit local lacks |
| `feat/mvp-foundation` | 2 | `origin/feat/mvp-foundation` | in sync |
| `feat/pipeline-observability` | 9 | none | never pushed |
| `p0-repo-triage` | 18 | none | never pushed; current branch |

`p0-repo-triage` was renamed from a name carrying prohibited framing. It had no upstream, so the
rename needed no history rewrite.

Both branches share `157a5be Initial commit` as their only merge base with `main`; the working
history diverged immediately and `main` holds a README only.

## Commit size against the 150-line ceiling

```
git log --all --format='%H' | while read -r c; do git show --shortstat --format='' "$c" | tail -1; done
```

**6 of 20 commits exceed 150 changed lines.** Insertions plus deletions, as `CLAUDE.md` defines it.

| lines | commit | reachable from | note |
|---|---|---|---|
| 15,868 | `b351431` Initialize … MVP foundation | `feat/mvp-foundation`, **published** | the anti-pattern `CLAUDE.md` names |
| 8,640 | `0e619fb` Add MVP scaffold with pipeline observability | `feat/pipeline-observability`, `p0-repo-triage` | second instance, on the current branch |
| 963 | `520ec77` Archive session-recovery and planning docs | `p0-repo-triage` | this triage; see below |
| 855 | `2b02576` Add validation tooling infrastructure | `p0-repo-triage` | |
| 516 | `98b7ea8` Add comprehensive implementation review | `p0-repo-triage` | |
| 261 | `8f5b053` Add ROADMAP.md | `p0-repo-triage` | introduced the ceiling rule, breaches it |

Two observations the rule as written does not resolve:

1. **The anti-pattern is not confined to an abandoned branch.** `CLAUDE.md` cites the 15,868-line
   commit, which lives only on `feat/mvp-foundation`. But `0e619fb` at 8,640 lines is an ancestor of
   the current branch, and is not cited anywhere.
2. **Three of the six breaches are documents that cannot be split.** `520ec77` archives three files
   of 455, 262 and 225 lines; committing each separately still breaches, because each exceeds 150 on
   its own. `8f5b053` and `98b7ea8` are single documents. A per-concern split has no effect on any
   of them — the unit of change is already one file.

## Published history

```
git tag -l; git branch -a --contains b351431
```

`origin` is `github.com/vaibhavhariram/curb`. One tag exists, `v0.1-mvp-scaffold`, pinned to
`b351431`, whose subject carries prohibited framing. The tag and the branch are both already on the
remote, so the subject cannot be corrected without a history rewrite of published refs, or by
deleting the tag and branch.

Commit subjects on the two unpushed branches were scanned for the same terms before pushing:

```
git log origin/main..HEAD --format='%h %s' | grep -icE 'palantir|foundry|gotham|chassis|world model|world graph|autonomous|robo-?taxi|self-driving'
```

Zero hits on `p0-repo-triage` and zero on `feat/pipeline-observability`.

## Working tree at time of measurement

Still uncommitted: `CLAUDE.md`, `supabase/migrations/007_validation_tooling.sql` and
`web/src/lib/utils/colors.ts` modified; `supabase/migrations/009_ingress_tables.sql` and the 13-file
ingress surface under `web/src/` untracked. These are held pending the ceiling-rule amendment, since
009 alone is 361 lines.
