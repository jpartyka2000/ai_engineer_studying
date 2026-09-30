# AI Interview Prep — Git & GitHub Workflow

This describes what this repository actually does, verified against its history. Where a
practice is aspirational rather than current, it says so instead of pretending.

## Repository

- `git@github.com:jpartyka2000/ai_engineer_studying.git`
- **Remote**: GitHub (`origin`)
- **Branch**: `main`, and only `main`. No `develop`, no feature branches.
- `main` is **not** branch-protected on GitHub. Pushes to it succeed.

---

## The one hard rule

**EVERY GIT COMMAND MUST BE CONFIRMED BY ME BEFORE IT RUNS.**

This applies to anything that changes state — `commit`, `push`, `checkout -b`, `reset`,
`rebase`, `tag`. Read-only inspection (`status`, `log`, `diff`, `show`) does not need
asking each time.

"Commit this" is confirmation to commit. It is **not** confirmation to push; ask
separately. Present the planned commit breakdown before running it, so the split can be
objected to while it is still cheap to change.

---

## Branching — trunk-based

Work goes directly onto `main`. Across 82 commits there are **zero merge commits, and no
branch other than `main` has ever existed**; the two-tier `main`/`develop` flow with
feature branches has never been used once.

Consequences worth being deliberate about:

- There is no integration branch, so `main` is only as deployable as the last commit.
  Run the checklist below *before* committing, not before some later merge.
- There is no review gate. The commit message is the only explanation anyone gets, which
  is why the body matters more here than in a repo with PRs.
- A half-finished change has nowhere to live. Either the commit stands on its own or it
  waits.

**If you do want a branch** — a risky refactor, an experiment you may throw away —
`feature/<short-description>`, `fix/<short-description>`, `refactor/<...>`,
`docs/<...>`, `test/<...>` off `main`. That is a deliberate exception, not the default,
and it needs confirming like any other git command.

---

## Commit Guidelines

### Commit Sizing — The Goldilocks Rule

Commits should be **right-sized**: meaningful and self-contained but not sprawling.

**Too small** (avoid): "Fix typo in variable name", "Add import statement", single-line
changes that don't stand alone.

**Too large** (avoid): "Implement entire exam mode" touching 20+ files across models,
views, templates and tests. Anything that would take more than ~30 minutes to review.

**Just right** (target): one logical unit of work you could explain in a single
sentence, which compiles, passes linting, and passes tests on its own.

- "Add Question model and migration" — one model, its migration, its admin registration
- "Implement exam scoring service with unit tests" — the service module plus its tests
- "Wire up Claude API for question generation" — the integration layer for one feature

Actual distribution: **median 5 files, p90 31 files.** The tail is real and mostly
legitimate:

- **`data` commits** (question and fixture exports) run to thousands of files. They are
  generated content, not code, and splitting them serves nobody.
- **Large `feat` commits** land when a module set is genuinely interdependent — a
  package whose parts cannot be committed separately without leaving dead code or code
  without its tests. When that happens, say so in the body rather than letting the size
  pass unremarked.

### Commit Message Format

```
<type>(<scope>): <short summary>

<body — explain WHY, not WHAT>

Co-Authored-By: ...
```

**Types**, by actual frequency:

| type | used | meaning |
|---|---|---|
| `feat` | 55 | New feature |
| `fix` | 11 | Bug fix |
| `chore` | 5 | Build, config, dependency changes |
| `data` | 4 | Generated content: question/fixture exports |
| `test` | 2 | Adding or modifying tests |
| `docs` | 2 | Documentation only |
| `style` | 1 | Formatting, linting (no logic change) |
| `refactor` | 0 | Restructuring with no behaviour change — available, never yet used |

**Scopes** are the app or area directory, not a fixed list. In use: `workspace`,
`visuals`, `questions`, `ui`, `exam`, `core`, `coding`, `config`, `admin`,
`systemdesign`, `accounts`, `lightning`, `qanda`, `equations`, `leetcode`, `azure`,
`sglang`, `fixtures`. Add a new one when a new app appears; a scope is omitted only for
changes that genuinely span the project (`style: apply ruff format across the project`).

**Footer.** `Co-Authored-By` appears on 80 of 82 commits — include it. There is **no
issue tracker in use**: `Refs #12` / `Fixes #42` have never appeared in this history, so
do not invent issue numbers. If a commit relates to something, name it in the body.

**Bodies carry real weight here.** With no PR description and no reviewer, the body is
the entire record of why a change was made. Write what a future reader could not
reconstruct from the diff: the reasoning, the alternatives rejected, what was measured,
what is still unresolved. The recent `workspace` commits are the reference for depth.

Examples from this repository:

```
fix(workspace): pass the check environment into the container

CheckRunner.run_command set env on the subprocess, which configures the local
`docker` CLI -- not the process inside the container. `docker compose exec`
forwards nothing by default, so CI_ENV silently applied to no containerised
check at all.

That made ci_env=True a no-op, including for flake_repeat, whose entire purpose
is reproducing CI-shaped nondeterminism under the environment CI actually uses.

Co-Authored-By: ...
```

```
feat(workspace): add the tenantsaas base application template

Co-Authored-By: ...
```

---

## Before committing or pushing

`main` has no safety net, so this runs before the commit rather than before a merge:

1. Tests pass: `pytest`
2. Linting passes: `ruff check .`
3. Formatting is clean: `ruff format --check .`
4. Migrations are up to date: `python manage.py makemigrations --check --dry-run`
5. Nothing untracked that should be committed, nothing staged that shouldn't:
   `git status`
6. Each commit's staged file list is what you intended — check it explicitly when
   splitting one body of work into several commits

Then, with confirmation:

```bash
git push origin main
```

---

## Not currently used

Named here so the difference between intent and practice stays visible. None of this is
set up; adopting any of it is a decision, not a default.

- **Pull requests.** No PR has ever been opened. Adopting them means creating branches
  and turning on branch protection, without which a PR is optional and gets skipped.
- **A `develop` integration branch.** Documented for a long time, never created. Only
  worth it if more than one change is ever in flight at once.
- **Branch protection on `main`.** Not configured. Until it is, "no direct pushes to
  main" is a preference rather than a rule, and nothing enforces the checklist above.
- **Tagged releases.** Zero tags across 82 commits. If releases start mattering:
  `git tag -a v1.x.0 -m "..."` and `git push origin v1.x.0`.
- **A hotfix process.** Meaningless while `main` is the only branch — a fix on `main`
  *is* the hotfix.

---

## .gitignore notes

`.gitignore` is a full Python/Django ignore set plus project-specific entries. Three are
load-bearing and easy to break:

```
workspaces/                  # scaffolded exercise repos; each is its own git repo
calibration/packets/         # regenerable from graded sessions
calibration/answer-key.json  # round-local; grades.json is NOT ignored - it is the corpus
!workspace_templates/**      # MUST stay last
```

The negation is the fragile one. Exercise templates are source and must stay tracked,
but several earlier rules (`lib/`, `.env*`, `*.sqlite3`, `media/`, `build/`) would
otherwise swallow template files silently. It only works as the final rule — adding an
ignore pattern after it can quietly drop template files from a commit.
