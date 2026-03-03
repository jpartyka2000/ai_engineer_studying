# AI Interview Prep — Feature Specification

## 1. Overview

A Django web application that helps users study for AI/ML engineering interviews and certifications. Users select a subject area and a study mode, then interact with dynamically generated content powered by the Claude API.

---

## 2. Subject Area Management

### 2.1 Subject Model

Each subject area is a database record with:

- **name**: Display name (e.g., "LightGBM")
- **slug**: URL-safe identifier
- **description**: Short blurb shown in the subject picker
- **category**: Grouping label (e.g., "ML Frameworks", "Python Core", "DevOps & Tooling")
- **icon**: Optional icon identifier for the UI
- **supports_visuals**: Boolean flag indicating whether Visuals mode is available for this subject
- **default_question_count**: Default number of questions for Exam mode (default: 10)
- **difficulty_levels**: JSON list of available difficulty tiers (default: `["beginner", "intermediate", "advanced"]`)
- **is_active**: Soft-disable toggle

### 2.2 Subject Picker

- Landing page displays all active subjects grouped by category.
- Each subject card shows name, description, and available modes.
- Search/filter bar for quickly finding subjects.
- After selecting a subject, the user is taken to a mode selection screen.

---

## 3. Study Modes

### 3.1 Exam Mode

**Purpose**: Simulated exam experience — answer a fixed number of questions, then receive a score and review.

**Flow**:

1. User selects subject and chooses Exam mode.
2. Configuration screen: choose number of questions (default from subject config) and difficulty level.
3. Questions are presented one at a time. Each question includes:
   - Question text (may include code snippets rendered with syntax highlighting).
   - Answer input: multiple choice (4 options) OR free-text, depending on the question.
   - A "Flag for review" button.
   - Navigation: "Next" button. No going back (to simulate real exam pressure).
4. After the last question, a confirmation screen: "Submit exam?"
5. Scoring screen:
   - Total score as fraction and percentage.
   - Per-question breakdown: your answer, correct answer, explanation.
   - Flagged questions highlighted.
   - Option to retry incorrect questions only.
6. Results are saved to the user's history.

**Question Generation**:

- Claude API generates questions in structured JSON format.
- Each question includes: `question_text`, `question_type` (mc or free), `options` (if mc), `correct_answer`, `explanation`, `difficulty`, `tags`.
- Generated questions are cached in the database keyed by (subject, difficulty, hash).
- If cached questions exist, prefer them; generate new ones only when the pool is thin.

### 3.2 Lightning Round Mode

**Purpose**: Answer as many questions as possible within a time limit.

**Flow**:

1. User selects subject and chooses Lightning Round mode.
2. Configuration screen: choose time limit in minutes (default: 5, options: 1, 2, 3, 5, 10, 15) and difficulty.
3. A countdown timer starts at the top of the screen. The timer is always visible.
4. Questions appear one at a time (multiple choice only, for speed).
5. As soon as the user selects an answer, immediate feedback is shown (correct/incorrect + brief explanation) for 1.5 seconds, then the next question auto-loads.
6. When time expires:
   - The current question is forfeited.
   - Results screen: total answered, total correct, accuracy percentage, average time per question.
7. Results saved to history.

**Question Generation**:

- Same pipeline as Exam mode but only multiple-choice questions.
- Pre-fetch a batch of 20 questions at session start; fetch more in the background as the user progresses.

### 3.3 Q&A Mode

**Purpose**: Open-ended conversation with Claude about a subject area. The user asks questions and gets detailed answers.

**Flow**:

1. User selects subject and chooses Q&A mode.
2. Chat-style interface. The system message primes Claude as an expert in the selected subject.
3. User types a question. Claude responds with a detailed, well-formatted answer.
4. Conversation history is maintained for the session.
5. Features:
   - Code snippets in responses are syntax-highlighted and copyable.
   - "Explain further" button on any response to ask for deeper detail.
   - "Give me an example" button to request a practical code example.
   - "Quiz me on this" button that generates a quick question from the current topic.
   - Conversation can be exported as Markdown.
6. Session history is saved for future reference.

**Claude Integration**:

- Streaming responses via the Anthropic SDK for real-time display.
- System prompt includes the subject area context and instructs Claude to be pedagogical, use examples, and cite best practices.
- Conversation history is sent with each request (up to context window limits; truncate oldest messages if needed).

### 3.4 Visuals Mode

**Purpose**: Interactive diagrams and visual explanations for subjects that benefit from visual learning.

**Available for**: Subjects where `supports_visuals` is True (e.g., Git, LightGBM, System Design, Neural Network architectures, Data Structures).

**Flow**:

1. User selects a subject with visuals support and chooses Visuals mode.
2. Topic picker: a list of visual topics for the subject (e.g., for LightGBM: "How a tree gets built", "Gradient computation", "Leaf-wise vs. level-wise growth").
3. Visual display:
   - Interactive, step-by-step diagram.
   - Play/pause controls and a step slider.
   - Each step has an accompanying text explanation panel.
   - For tree-building visuals: show nodes being added one at a time, with split decisions and gain values.
4. "Explain this step" button sends the current visual context to Claude for a deeper explanation.

**Visual Generation**:

- Visuals are defined as a series of states (frames), each with diagram data + explanation text.
- Diagram rendering: Mermaid.js for flowcharts/trees, D3.js for custom interactive visuals, server-generated SVG/PNG via graphviz or matplotlib for static diagrams.
- Visual definitions are stored in the database and can be pre-generated or generated on-demand via Claude.
- Claude is prompted to produce a JSON array of visual steps, each containing structured diagram data and explanation text.

**Example — LightGBM Tree Building**:

- Step 0: Show training data (small sample) in a table.
- Step 1: Calculate initial prediction (mean of target).
- Step 2: Calculate residuals.
- Step 3: Find best split for root node. Highlight the feature and threshold. Show gain.
- Step 4: Create two child nodes. Show data distribution.
- Steps 5–N: Repeat splitting for each leaf until stopping criteria met.
- Final: Show complete tree with all splits and leaf values.

---

## 4. User System

### 4.1 Authentication

- Django's built-in auth system.
- Email/password registration.
- Social auth (Google, GitHub) via `django-allauth` (future enhancement).
- Password reset flow.

### 4.2 User Profile & Progress

- Dashboard showing:
  - Total study time.
  - Exams taken, average score, score trend over time.
  - Lightning round stats: best streak, average accuracy.
  - Most-studied subjects.
  - Weakest topics (subjects/tags with lowest scores).
- Per-subject progress breakdown.
- Study streak tracking (days in a row with at least one session).

---

## 5. Data Models Summary

- **Subject**: name, slug, category, description, supports_visuals, default_question_count, difficulty_levels, is_active
- **Question**: subject (FK), question_text, question_type, options (JSON), correct_answer, explanation, difficulty, tags (JSON), source_hash, created_at
- **ExamSession**: user (FK), subject (FK), difficulty, question_count, score, started_at, completed_at
- **ExamAnswer**: session (FK), question (FK), user_answer, is_correct, is_flagged
- **LightningSession**: user (FK), subject (FK), difficulty, time_limit_seconds, questions_answered, questions_correct, started_at, completed_at
- **QASession**: user (FK), subject (FK), started_at, messages (JSON or related model)
- **VisualTopic**: subject (FK), title, slug, description, steps (JSON), rendering_type
- **UserProgress**: user (FK), subject (FK), total_sessions, total_correct, total_questions, last_studied_at

---

## 6. API Endpoints (Internal)

All views are server-rendered Django views with HTMX for dynamic updates. No separate REST API is needed initially, but the architecture should support adding one via Django REST Framework later.

Key URL patterns:

- `/` — Landing page / subject picker
- `/subject/<slug>/` — Subject detail with mode selection
- `/subject/<slug>/exam/` — Exam mode config
- `/subject/<slug>/exam/session/<id>/` — Active exam session
- `/subject/<slug>/exam/session/<id>/results/` — Exam results
- `/subject/<slug>/lightning/` — Lightning round config
- `/subject/<slug>/lightning/session/<id>/` — Active lightning round
- `/subject/<slug>/lightning/session/<id>/results/` — Lightning results
- `/subject/<slug>/qa/` — Q&A mode (new session)
- `/subject/<slug>/qa/<id>/` — Existing Q&A session
- `/subject/<slug>/visuals/` — Visual topics list
- `/subject/<slug>/visuals/<topic-slug>/` — Visual viewer
- `/dashboard/` — User dashboard
- `/accounts/` — Auth (login, register, password reset)

---

## 7. Non-Functional Requirements

- **Performance**: Question generation should feel fast. Use background pre-fetching and caching. Streaming for Q&A responses.
- **Accessibility**: Semantic HTML, ARIA labels, keyboard navigable, sufficient color contrast.
- **Responsive Design**: Mobile-friendly. Exam and Lightning modes must work well on phones.
- **Security**: CSRF protection, rate limiting on Claude API calls, input sanitization, no XSS.
- **Cost Management**: Cache questions aggressively. Track API usage per user. Implement daily/hourly usage caps.

---

## 8. Implementation Phases

### Phase 1: Foundation
- Django project scaffolding, settings, database setup.
- User auth (register, login, logout).
- Subject model and admin interface.
- Subject picker page.

### Phase 2: Exam Mode
- Question model and Claude-powered generation service.
- Exam session flow (config → questions → scoring → results).
- Question caching.

### Phase 3: Lightning Round
- Lightning session flow with countdown timer.
- Background question pre-fetching.
- Immediate feedback UI.

### Phase 4: Q&A Mode
- Chat interface with streaming responses.
- Conversation history management.
- Quick-action buttons (explain further, give example, quiz me).

### Phase 5: Visuals Mode
- Visual topic model and step-based viewer.
- Mermaid.js and D3.js rendering.
- Claude-powered visual generation.
- LightGBM tree-building visual as flagship example.

### Phase 6: Dashboard & Polish
- User progress tracking and dashboard.
- Study streak system.
- Performance optimization and caching.
- UI polish and mobile responsiveness.
