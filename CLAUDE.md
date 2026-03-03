# AI Interview Prep - Claude Code Instructions

## Project Overview

This is a Django web application for studying AI/ML engineering interview topics. It provides multiple study modes across dozens of subject areas, powered by the Claude API for dynamic question generation and interactive learning.

## Tech Stack

- **Backend**: Django 5.x (Python 3.12+)
- **Frontend**: Django templates + HTMX + Tailwind CSS
- **Database**: PostgreSQL (development and production)
- **AI Integration**: Anthropic Claude API (claude-sonnet-4-5-20250929)
- **Task Queue**: Celery + Redis (for async question generation and scoring)
- **Testing**: pytest + pytest-django + pytest-cov
- **Visuals**: Mermaid.js, D3.js, and server-side diagram generation via matplotlib/graphviz

## Project Structure

```
ai-interview-prep/
├── CLAUDE.md                  # You are here
├── spec.md                    # Feature specification
├── TESTING.md                 # Testing strategy and instructions
├── GITHUB.md                  # Git workflow and commit guidelines
├── .claude/
│   └── settings.json          # Claude Code configuration
├── manage.py
├── config/                    # Django project settings
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── prod.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── core/                  # Shared models, utilities, base templates
│   ├── subjects/              # Subject area management
│   ├── questions/             # Question bank and generation
│   ├── exam/                  # Exam mode
│   ├── lightning/             # Lightning Round mode
│   ├── qanda/                 # Q&A mode
│   ├── visuals/               # Visuals/diagram mode
│   └── accounts/              # User auth and progress tracking
├── templates/
│   ├── base.html
│   └── ...                    # App-specific templates
├── static/
│   ├── css/
│   ├── js/
│   └── img/
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── regression/
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
└── docker-compose.yml
```

## Coding Standards

- Follow PEP 8 strictly. Use `ruff` for linting and formatting.
- Use type hints on all function signatures (new-style syntax where possible: `list[str]`, `dict[str, int]`, `X | None`). Import `Any`, `Literal`, `Final`, `TypeVar`, etc. from `typing` when needed.
- Use dataclasses or Pydantic models for structured data passed between layers.
- Django models: use explicit `Meta` classes, define `__str__`, add `help_text` to fields.
- Django views: prefer class-based views. Keep business logic out of views — use service modules under each app.
- All user-facing strings must be translatable using `gettext_lazy`.
- Keep functions short. If a function exceeds ~30 lines, consider splitting it.
- Docstrings on all public classes and functions (Google style).
- No hardcoded secrets. Use environment variables via `django-environ`.

## Key Commands

```bash
# Development
python manage.py runserver
python manage.py makemigrations
python manage.py migrate

# Testing (see TESTING.md for full details)
pytest                                # Run all tests
pytest tests/unit/                    # Unit tests only
pytest tests/integration/             # Integration tests only
pytest tests/regression/              # Regression tests only
pytest --cov=apps --cov-report=html   # Coverage report

# Linting
ruff check .
ruff format .

# Django management
python manage.py createsuperuser
python manage.py collectstatic
python manage.py shell_plus           # Enhanced Django shell
```

## Claude API Integration

- Use the `anthropic` Python SDK.
- All API calls go through a centralized service layer at `apps/core/services/claude_service.py`.
- Never expose the API key in code. Use the `ANTHROPIC_API_KEY` environment variable.
- Use structured prompts with system messages that constrain output format.
- For question generation, request JSON responses and validate with Pydantic.
- Implement retry logic with exponential backoff for API failures.
- Cache generated questions in the database to minimize redundant API calls.

## Working Conventions

- Always read `spec.md` before implementing a new feature to understand requirements.
- Always read `TESTING.md` before writing tests.
- Always read `GITHUB.md` before committing.
- When creating a new Django app, register it in `INSTALLED_APPS`, create migrations, and add URL patterns.
- When modifying models, always create and apply migrations before moving on.
- Run `ruff check . && ruff format .` before every commit.
- Never modify files outside the project directory.

## Subject Areas

The application supports (but is not limited to) these subject areas:

Python OOP, LightGBM, OpenAI Agents SDK, Pydantic, Pydantic AI, scikit-learn, Python logging, Python typing, Git, Pandas, PySpark, MLflow, Transformers (Hugging Face), PyTorch, TensorFlow/Keras, SQL, System Design, Docker, Kubernetes, FastAPI, REST API Design, Data Structures & Algorithms, Statistics & Probability, A/B Testing, Feature Engineering, Model Evaluation, NLP, Computer Vision, Reinforcement Learning, LangChain, Vector Databases, RAG, Prompt Engineering.

Subject areas are stored in the database and are admin-configurable. New subjects can be added without code changes.

## Error Handling

- Use Django's logging framework. Configure structured logging (JSON format) in production.
- All Claude API errors must be caught, logged, and presented to the user with a friendly message.
- Use Django's message framework for user-facing notifications.
- Custom exception classes live in `apps/core/exceptions.py`.
