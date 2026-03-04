# AI Interview Prep - Implementation Plan

## Overview

This document tracks the implementation progress of the AI Interview Prep application across 6 phases.

---

## Phase 1: Foundation ✅ COMPLETE

**Status:** Implemented in commit `c261a82`

### Tasks
- [x] Django project scaffolding, settings, database setup
- [x] User auth (register, login, logout)
- [x] Subject model and admin interface
- [x] Subject picker page

### What Was Built
- Subject model with all spec fields (name, slug, category, supports_visuals, difficulty_levels, etc.)
- User authentication views and templates (register, login, logout, profile)
- Subject picker landing page grouped by category with search
- Subject detail page with mode selection
- Base template with navigation and mobile menu

### Key Files
- `apps/subjects/models.py` - Subject model
- `apps/accounts/views.py`, `forms.py` - Auth views
- `templates/accounts/` - Auth templates
- `templates/core/home.html` - Subject picker
- `templates/subjects/detail.html` - Mode selection

---

## Phase 2: Exam Mode ✅ COMPLETE

**Status:** Implemented in commit `1f414a1`

### Tasks
- [x] Question model and Claude-powered generation service
- [x] Exam session flow (config → questions → scoring → results)
- [x] Question caching

### What Was Built
- Question model with source tracking (llm_studying, claude_api, manual)
- ExamSession and ExamAnswer models
- Claude-powered question generation service
- Management command to import questions from `llm_studying/` directory
- Auto-mapping of folder names to Subject records
- Complete exam flow with configuration, question display, and results
- Question deduplication via content hashing

### Key Files
- `apps/questions/models.py` - Question model
- `apps/exam/models.py` - ExamSession, ExamAnswer
- `apps/questions/services/question_generator.py` - Claude integration
- `apps/questions/management/commands/import_questions.py` - Import command
- `apps/exam/views.py` - Exam flow views
- `templates/exam/` - Exam templates (config, question, submit, results)

### Usage
```bash
# List available subjects from llm_studying
python manage.py import_questions --list-subjects

# Create subjects without importing questions (no API key needed)
python manage.py import_questions --create-subjects-only

# Import questions for a subject (requires ANTHROPIC_API_KEY)
python manage.py import_questions --subject python --max-files 5
```

### Notes
- Requires `ANTHROPIC_API_KEY` environment variable for question generation
- Questions are stored in database for caching/reuse
- Supports both multiple choice and free text questions

---

## Phase 3: Lightning Round ✅ COMPLETE

### Tasks
- [x] Lightning session flow with countdown timer
- [x] Immediate feedback UI with auto-advance
- [x] Results page with stats and review

### What Was Built
- LightningSession and LightningAnswer models with streak tracking
- Time limit choices (1, 2, 3, 5, 10, 15 minutes)
- Real-time countdown timer with progress bar
- Live stats display (answered, correct, streak, accuracy)
- Instant feedback after each answer with correct answer and explanation
- Auto-advance to next question after 2 second delay
- Results page showing all answers with response times
- Admin interface for managing lightning sessions

### Key Files
- `apps/lightning/models.py` - LightningSession, LightningAnswer models
- `apps/lightning/views.py` - Config, play, results views
- `apps/lightning/admin.py` - Admin configuration
- `apps/lightning/urls.py` - URL patterns
- `templates/lightning/config.html` - Configuration page
- `templates/lightning/play.html` - Main gameplay with timer and feedback
- `templates/lightning/results.html` - Results and review page
- `apps/core/templatetags/core_tags.py` - Custom template tags

---

## Phase 4: Q&A Mode ✅ COMPLETE

### Tasks
- [x] Chat interface with streaming responses
- [x] Conversation history management
- [x] Quick-action buttons (explain further, give example, quiz me)

### What Was Built
- QASession model with status management (active/archived)
- Message model with separate user/assistant messages and metadata tracking
- Server-Sent Events (SSE) streaming for real-time Claude responses
- Token-aware conversation history with sliding window truncation
- Complete chat interface with message history and input form
- Three quick-action buttons on each assistant message:
  - "Explain Further" - request more detail
  - "Give Example" - request practical code example
  - "Quiz Me" - generate practice question
- Real-time markdown rendering with marked.js
- Code syntax highlighting with Prism.js (Python, JavaScript, Bash, SQL)
- Export conversation as downloadable markdown file
- Archive session functionality
- Admin interfaces for QASession and Message management

### Key Files
- `apps/qanda/models.py` - QASession and Message models
- `apps/qanda/views.py` - All Q&A views including SSE streaming
- `apps/qanda/admin.py` - Admin configuration
- `apps/qanda/urls.py` - URL patterns
- `apps/core/services/claude_service.py` - Added stream_completion() method
- `templates/qanda/home.html` - Session list page
- `templates/qanda/session.html` - Chat interface with streaming JavaScript
- `templates/subjects/detail.html` - Added Q&A Mode link

### Features Implemented
1. **Streaming Responses**: Real-time Claude responses via SSE (Server-Sent Events)
2. **Conversation Management**: Full history with token-based truncation (100k token limit)
3. **Quick Actions**: Three contextual buttons on each assistant message
4. **Code Highlighting**: Automatic syntax highlighting for code blocks
5. **Markdown Rendering**: Rich formatting with marked.js
6. **Export**: Download conversations as markdown files
7. **Archive**: Archive old sessions to keep workspace clean
8. **Session Management**: Multiple sessions per subject, resume anytime

### Technical Details
- **Streaming**: EventSource API (client) + StreamingHttpResponse (server)
- **Token Counting**: Approximate estimation (4 chars ≈ 1 token)
- **Context Window**: Keeps last ~100k tokens in conversation history
- **Message Storage**: Separate Message records for flexible querying
- **Error Handling**: Graceful degradation on streaming errors
- **Security**: User isolation, CSRF protection, input validation

---

## Phase 5: Visuals Mode 🔲 NOT STARTED

### Tasks
- [ ] Visual topic model and step-based viewer
- [ ] Mermaid.js and D3.js rendering
- [ ] Claude-powered visual generation
- [ ] LightGBM tree-building visual as flagship example

### Planned Features
- Interactive step-by-step diagrams
- Play/pause controls and step slider
- Text explanations for each step
- "Explain this step" button for Claude integration
- Support for: Mermaid.js (flowcharts), D3.js (custom visuals), server-generated SVG/PNG

### Key Models Needed
- `VisualTopic` - subject, title, slug, description, steps (JSON), rendering_type

---

## Phase 6: Dashboard & Polish 🔲 NOT STARTED

### Tasks
- [ ] User progress tracking and dashboard
- [ ] Study streak system
- [ ] Performance optimization and caching
- [ ] UI polish and mobile responsiveness

### Planned Features
- Dashboard showing:
  - Total study time
  - Exams taken, average score, score trends
  - Lightning round stats
  - Most-studied subjects
  - Weakest topics
- Per-subject progress breakdown
- Study streak tracking (consecutive days)

### Key Models Needed
- `UserProgress` - user, subject, total_sessions, total_correct, total_questions, last_studied_at

---

## Quick Reference

### Running the App
```bash
# Activate virtual environment
source venv/bin/activate

# Run migrations
python manage.py migrate --settings=config.settings.dev

# Create superuser
python manage.py createsuperuser --settings=config.settings.dev

# Run development server
python manage.py runserver --settings=config.settings.dev
```

### Environment Variables
```bash
# Required for question generation
export ANTHROPIC_API_KEY=sk-ant-your-key-here

# Optional: Use PostgreSQL instead of SQLite
export USE_POSTGRES=True
export DB_NAME=ai_interview_prep
export DB_USER=postgres
export DB_PASSWORD=postgres
```

### Key URLs
- `/` - Subject picker (home)
- `/subject/<slug>/` - Subject detail with mode selection
- `/exam/<slug>/` - Exam configuration
- `/admin/` - Django admin
- `/accounts/login/` - Login
- `/accounts/register/` - Registration
