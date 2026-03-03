# AI Interview Prep — Git & GitHub Workflow

## Repository

- git@github.com:jpartyka2000/ai_engineer_studying.git
- **Remote**: GitHub (origin)
- **Main branch**: `main` — always deployable, protected.
- **Development branch**: `develop` — integration branch for features.
- FOR EVERY GIT COMMAND YOU RUN, IT MUST BE CONFIRMED BY ME.

---

## Branching Strategy

Use feature branches off `develop`:

```
main          ← production-ready, tagged releases
  └── develop ← integration branch
        ├── feature/exam-mode
        ├── feature/lightning-round
        ├── fix/scoring-bug-42
        └── ...
```

Branch naming conventions:
- `feature/<short-description>` — New functionality (e.g., `feature/exam-scoring`)
- `fix/<short-description>` — Bug fixes (e.g., `fix/timer-overflow`)
- `refactor/<short-description>` — Code improvements with no behavior change
- `docs/<short-description>` — Documentation only
- `test/<short-description>` — Adding or improving tests only

---

## Commit Guidelines

### Commit Sizing — The Goldilocks Rule

Commits should be **right-sized**: meaningful and self-contained but not sprawling.

**Too small** (avoid):
- "Fix typo in variable name"
- "Add import statement"
- "Update whitespace"
- Single-line changes that don't stand alone.

**Too large** (avoid):
- "Implement entire exam mode" (touching 20+ files across models, views, templates, tests)
- "Add all subject areas and question generation"
- Changes that take more than ~30 minutes to code review.

**Just right** (target):
- "Add Question model and migration" — One model, its migration, and its admin registration.
- "Implement exam scoring service with unit tests" — The service module plus its tests.
- "Add exam session views and URL routing" — Views + URLs + basic templates for one flow.
- "Wire up Claude API for question generation" — The integration layer for one specific feature.

**Rule of thumb**: A commit should represent one logical unit of work that you could explain in a single sentence. It should compile, pass linting, and ideally pass tests on its own.

### Commit Message Format

Use conventional commits:

```
<type>(<scope>): <short summary>

<optional body — explain WHY, not WHAT>

<optional footer — reference issues>
```

Types:
- `feat` — New feature
- `fix` — Bug fix
- `refactor` — Code restructuring, no behavior change
- `test` — Adding or modifying tests
- `docs` — Documentation changes
- `style` — Formatting, linting fixes (no logic changes)
- `chore` — Build, config, dependency changes

Scopes (match Django apps):
- `core`, `subjects`, `questions`, `exam`, `lightning`, `qanda`, `visuals`, `accounts`, `config`

Examples:

```
feat(exam): add ExamSession model and migration

Defines the ExamSession model with FK to user and subject,
score tracking, and timestamps. Includes initial migration.

Refs #12

---

feat(questions): implement Claude-powered question generation service

Adds QuestionGenerationService that calls the Claude API to generate
structured multiple-choice and free-text questions. Includes retry
logic, response validation via Pydantic, and caching to the Question
model.

Refs #15

---

fix(lightning): prevent timer from going negative on slow connections

The countdown timer could display negative values if the HTMX poll
response was delayed. Now clamps to zero client-side and triggers
session end immediately.

Fixes #42

---

test(exam): add integration tests for full exam flow

Tests the complete path: start session → answer questions → submit →
view results. Uses mocked Claude API responses. Covers both
all-correct and mixed-result scenarios.

Refs #12
```

---

## Push Workflow

### When to Push

Push to the remote after completing each logical unit of work. Align pushes with the commit sizing guidelines above. A typical feature will involve 3–8 commits pushed together or incrementally:

Example for "Exam Mode":
1. `feat(questions): add Question model and migration`
2. `feat(exam): add ExamSession and ExamAnswer models`
3. `feat(questions): implement question generation service`
4. `feat(exam): add exam session views and templates`
5. `feat(exam): implement scoring and results display`
6. `test(exam): add unit tests for scoring service`
7. `test(exam): add integration tests for exam flow`
8. `docs(exam): update spec.md with implementation notes`

### Push Checklist

Before every push, verify:

1. All tests pass: `pytest`
2. Linting passes: `ruff check .`
3. Formatting is clean: `ruff format .`
4. No untracked files that should be committed: `git status`
5. Migrations are up to date: `python manage.py makemigrations --check`
6. You are on the correct branch (not `main` or `develop` directly).

### Push Commands

```bash
# Standard push
git push origin feature/exam-mode

# First push of a new branch
git push -u origin feature/exam-mode
```

---

## Pull Request Process

When a feature is complete (all commits pushed, all tests passing):

1. Open a PR from `feature/xxx` → `develop`.
2. PR title follows the same conventional commit format: `feat(exam): implement exam mode`.
3. PR description includes:
   - Summary of changes.
   - Link to relevant spec section.
   - Screenshot/GIF if UI changes are involved.
   - Test coverage summary.
4. All CI checks must pass.
5. Squash-merge into `develop` to keep history clean.

---

## Release Process

When `develop` is stable and ready for release:

1. Merge `develop` → `main` (no squash, preserve history).
2. Tag the release: `git tag -a v1.x.0 -m "Release v1.x.0: <summary>"`.
3. Push tag: `git push origin v1.x.0`.

---

## .gitignore Essentials

Ensure these are in `.gitignore`:

```
__pycache__/
*.pyc
*.pyo
.env
.env.*
db.sqlite3
*.sqlite3
media/
staticfiles/
htmlcov/
.coverage
.pytest_cache/
.ruff_cache/
node_modules/
.claude/settings.local.json
*.log
```

---

## Protected Branch Rules

- `main`: No direct pushes. Requires PR with passing CI. No force pushes.
- `develop`: No direct pushes. Requires PR with passing CI.

---

## Emergency Hotfix Process

For critical production bugs:

1. Branch from `main`: `git checkout -b hotfix/critical-bug main`
2. Fix, test, commit.
3. PR into both `main` and `develop`.
4. Tag a patch release on `main`.
