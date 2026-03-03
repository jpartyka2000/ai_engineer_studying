# AI Interview Prep — Testing Instructions

## Core Principle

Every feature must have tests before it is considered complete. No feature branch is merged without passing unit tests, integration tests, and relevant regression tests.

---

## Test Structure

All tests live in the `tests/` directory at the project root, organized as follows:

```
tests/
├── conftest.py                # Shared fixtures (db, client, users, subjects, mock Claude API)
├── unit/                      # Fast, isolated tests for individual functions and classes
│   ├── test_models.py
│   ├── test_services.py
│   ├── test_forms.py
│   ├── test_utils.py
│   └── ...
├── integration/               # Tests that exercise multiple components together
│   ├── test_exam_flow.py
│   ├── test_lightning_flow.py
│   ├── test_qa_flow.py
│   ├── test_visuals_flow.py
│   ├── test_claude_api.py
│   └── ...
└── regression/                # Tests for previously fixed bugs (never delete these)
    ├── test_issue_NNN.py      # Named by issue/ticket number
    └── ...
```

---

## Test Categories

### Unit Tests (`tests/unit/`)

Test individual functions, methods, and classes in isolation.

Requirements:
- No database access (use mocks or Django's `SimpleTestCase` where possible).
- No external API calls. Always mock the Claude API client.
- No file system side effects.
- Each test should run in under 100ms.
- Name test functions descriptively: `test_<function_name>_<scenario>_<expected_result>`.
  Example: `test_calculate_score_all_correct_returns_100_percent`.

What to test:
- Model methods and properties.
- Service layer business logic.
- Form validation (valid and invalid inputs).
- Utility functions (string formatting, data transformers, etc.).
- Question parsing and validation logic.
- Prompt construction for Claude API calls.

### Integration Tests (`tests/integration/`)

Test interactions between multiple components: views, services, database, and (mocked) external APIs.

Requirements:
- Use Django's `TestCase` (with database access via transactions).
- Mock the Claude API at the HTTP level using `responses` or `httpx_mock`, not at the service level. This ensures the full service → SDK → HTTP path is exercised.
- Test complete user flows end-to-end within the Django application.
- Test HTMX interactions by asserting on response fragments.

What to test:
- Full exam flow: start session → answer questions → submit → view results.
- Lightning round flow: start → answer under time → session ends → view results.
- Q&A flow: send message → receive response → conversation history maintained.
- Visuals flow: select topic → step through visual → request explanation.
- Auth flows: register → login → access protected pages → logout.
- Subject picker: filtering, searching, mode availability.
- Error handling: Claude API failures gracefully handled, user sees friendly errors.

### Regression Tests (`tests/regression/`)

Tests for bugs that have been found and fixed. These ensure we never reintroduce a known bug.

Requirements:
- Every bug fix commit must include a regression test.
- Name the test file after the issue number: `test_issue_42.py`.
- Include a docstring describing the original bug and when it was fixed.
- Never delete regression tests, even if the related code is refactored.

Example:

```python
class TestIssue42:
    """
    Bug: Exam scoring counted flagged-but-unanswered questions as incorrect
    instead of skipped. Fixed: 2025-01-15.
    """
    def test_flagged_unanswered_counted_as_skipped(self, exam_session):
        ...
```

---

## Fixtures and Factories

Use `conftest.py` for shared fixtures. Use `factory_boy` for model factories.

Required fixtures (define in `tests/conftest.py`):

- `db_session` — Ensures the test database is available.
- `user` — A basic authenticated user.
- `admin_user` — A staff/superuser.
- `subject` — A sample subject (Python OOP by default).
- `subject_with_visuals` — A subject with `supports_visuals=True` (LightGBM).
- `question_bank` — A set of 20 pre-generated questions for a subject.
- `mock_claude_api` — Patches the Anthropic client to return deterministic responses.

Required factories (define in `tests/factories.py`):

- `SubjectFactory`
- `QuestionFactory`
- `ExamSessionFactory`
- `LightningSessionFactory`
- `QASessionFactory`
- `UserFactory`

---

## Mocking the Claude API

All tests that involve Claude API interactions must use mocks. Never make real API calls in tests.

The mock should be configurable to return:
- A valid question generation response (structured JSON).
- A valid Q&A response (streaming text).
- A valid visual generation response (JSON array of steps).
- An error response (rate limit, server error, timeout).

Define the mock in `tests/conftest.py`:

```python
@pytest.fixture
def mock_claude_api(monkeypatch):
    """Mock the Claude API client for deterministic test responses."""
    # Implementation should patch anthropic.Anthropic or the service layer
    ...
```

---

## Running Tests

```bash
# Run everything
pytest

# Run with verbose output
pytest -v

# Run specific category
pytest tests/unit/
pytest tests/integration/
pytest tests/regression/

# Run tests for a specific app
pytest tests/unit/ -k "exam"

# Run with coverage
pytest --cov=apps --cov-report=html --cov-report=term-missing

# Run only fast tests (unit)
pytest tests/unit/ -x --timeout=10

# Run tests matching a pattern
pytest -k "test_scoring"
```

---

## Coverage Requirements

- Overall project coverage target: 80% minimum.
- Service layer coverage target: 90% minimum.
- Model layer coverage target: 85% minimum.
- View layer coverage target: 75% minimum.
- Coverage is checked in CI. A PR that drops coverage below thresholds will fail.

---

## Test-Driven Feature Development Workflow

When building a new feature, follow this order:

1. Read the relevant section of `spec.md`.
2. Write unit tests for the new models and service functions (they will fail).
3. Implement the models and service layer until unit tests pass.
4. Write integration tests for the full user flow (they will fail).
5. Implement views, templates, and URL routing until integration tests pass.
6. Run the full test suite to ensure nothing is broken.
7. Run `ruff check . && ruff format .`.
8. Commit (see `GITHUB.md` for commit guidelines).

---

## Continuous Integration Checks

Every push and PR must pass:

1. `ruff check .` — No linting errors.
2. `ruff format --check .` — Code is formatted.
3. `pytest tests/unit/` — All unit tests pass.
4. `pytest tests/integration/` — All integration tests pass.
5. `pytest tests/regression/` — All regression tests pass.
6. `pytest --cov=apps` — Coverage meets thresholds.
7. `python manage.py check --deploy` — Django deployment checks pass.
8. `python manage.py makemigrations --check` — No unapplied migration changes.

---

## Testing Conventions

- Use `pytest` style (plain functions and classes), not `unittest.TestCase` unless database transactions are needed.
- Use `pytest.mark.parametrize` for testing multiple inputs on the same logic.
- Use `pytest.mark.slow` for tests that take >2 seconds; these can be skipped during rapid development with `-m "not slow"`.
- Use `freezegun` for time-dependent tests (lightning round timers, study streaks).
- Assert specific values, not just truthiness. `assert score == 0.75` not `assert score`.
- Test both happy paths and error paths. Every service function should have at least one test for expected failures.
