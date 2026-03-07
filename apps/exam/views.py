"""Views for the exam app."""

import logging
import random

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, TemplateView

from apps.questions.models import Question
from apps.subjects.models import Subject

from .models import ExamAnswer, ExamSession

logger = logging.getLogger(__name__)


class ExamConfigView(LoginRequiredMixin, TemplateView):
    """Configure exam settings before starting."""

    template_name = "exam/config.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subject = get_object_or_404(
            Subject, slug=kwargs["subject_slug"], is_active=True
        )
        context["subject"] = subject

        # Get available question count for each difficulty
        difficulties = {}
        for level in subject.difficulty_levels:
            if level == "interview":
                # Interview mode uses all questions regardless of difficulty
                count = Question.objects.filter(
                    subject=subject,
                    is_active=True,
                ).count()
            else:
                count = Question.objects.filter(
                    subject=subject,
                    difficulty=level,
                    is_active=True,
                ).count()
            difficulties[level] = count

        context["difficulties"] = difficulties
        context["default_count"] = subject.default_question_count
        return context


@login_required
@require_POST
def start_exam(request, subject_slug):
    """Start a new exam session."""
    subject = get_object_or_404(Subject, slug=subject_slug, is_active=True)

    # Get configuration from form
    difficulty = request.POST.get("difficulty", "intermediate")
    practice_mode = request.POST.get("practice_mode") == "1"
    try:
        question_count = int(
            request.POST.get("question_count", subject.default_question_count)
        )
    except ValueError:
        question_count = subject.default_question_count

    # Validate question count
    question_count = max(1, min(question_count, 50))

    # Handle interview mode specially
    if difficulty == "interview":
        selected_ids = _get_interview_questions(
            request, subject, question_count, subject_slug
        )
        if selected_ids is None:
            # Error occurred, redirect handled in helper
            return redirect("exam:config", subject_slug=subject_slug)
    else:
        # Standard difficulty filtering
        available_questions = list(
            Question.objects.filter(
                subject=subject,
                difficulty=difficulty,
                is_active=True,
            ).values_list("id", flat=True)
        )

        if len(available_questions) < question_count:
            messages.warning(
                request,
                _(
                    f"Only {len(available_questions)} questions available for {difficulty} difficulty."
                ),
            )
            question_count = len(available_questions)

        if question_count == 0:
            messages.error(
                request,
                _(
                    "No questions available for this subject and difficulty. Please try a different configuration."
                ),
            )
            return redirect("exam:config", subject_slug=subject_slug)

        # Select random questions
        selected_ids = random.sample(available_questions, question_count)

    # Create exam session
    session = ExamSession.objects.create(
        user=request.user,
        subject=subject,
        difficulty=difficulty,
        question_count=len(selected_ids),
        is_practice=practice_mode,
    )

    # Create exam answers (question slots) - preserve order for interview mode
    questions_by_id = {q.id: q for q in Question.objects.filter(id__in=selected_ids)}
    for i, qid in enumerate(selected_ids):
        if qid in questions_by_id:
            ExamAnswer.objects.create(
                session=session,
                question=questions_by_id[qid],
                order=i,
            )

    return redirect("exam:question", subject_slug=subject_slug, pk=session.pk)


def _get_interview_questions(request, subject, question_count, subject_slug):
    """
    Get questions for interview mode using LLM ranking.

    Returns list of question IDs or None if error occurred.
    """
    from apps.core.services.llm_service import LLMAPIError
    from apps.questions.services.interview_ranker import (
        QuestionForRanking,
        get_interview_ranker,
    )

    # Get all questions (any difficulty), limit to 50 for LLM
    available_questions = list(
        Question.objects.filter(
            subject=subject,
            is_active=True,
        ).values("id", "question_text", "options", "difficulty", "tags")[:50]
    )

    if len(available_questions) == 0:
        messages.error(
            request,
            _("No questions available for this subject. Please try a different subject."),
        )
        return None

    # If we have more than 50, randomly sample
    if len(available_questions) > 50:
        available_questions = random.sample(available_questions, 50)

    # Adjust question count if needed
    actual_count = min(question_count, len(available_questions))
    if actual_count < question_count:
        messages.warning(
            request,
            _(f"Only {actual_count} questions available for interview mode."),
        )

    # Convert to Pydantic models for ranking
    questions_for_ranking = [
        QuestionForRanking(
            id=q["id"],
            question_text=q["question_text"],
            options=q["options"] or [],
            difficulty=q["difficulty"],
            tags=q["tags"] or [],
        )
        for q in available_questions
    ]

    # Rank via LLM
    ranker = get_interview_ranker()

    try:
        selected_ids = ranker.rank_questions(
            questions=questions_for_ranking,
            subject_name=subject.name,
            num_to_select=actual_count,
        )
        return selected_ids
    except LLMAPIError as e:
        logger.exception("Interview ranking failed for %s: %s", subject.slug, e)
        messages.error(
            request,
            _(
                "Unable to generate interview-focused questions. "
                "Please try again or select a different difficulty."
            ),
        )
        return None


class ExamQuestionView(LoginRequiredMixin, DetailView):
    """Display current question in an exam session."""

    model = ExamSession
    template_name = "exam/question.html"
    context_object_name = "session"

    def get_queryset(self):
        return ExamSession.objects.filter(
            user=self.request.user,
            status=ExamSession.Status.IN_PROGRESS,
        ).select_related("subject")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object

        # Get current answer slot
        answers = list(session.answers.select_related("question").order_by("order"))
        if session.current_question_index < len(answers):
            current_answer = answers[session.current_question_index]
            context["current_answer"] = current_answer
            context["question"] = current_answer.question
            context["question_number"] = session.current_question_index + 1
            context["total_questions"] = session.question_count
            context["progress_percent"] = int(
                (session.current_question_index / session.question_count) * 100
            )

            # Find prerequisite questions (related questions from same subject)
            context["prerequisite_questions"] = self._get_prerequisite_questions(
                current_answer.question, session.subject
            )
        else:
            # All questions answered, redirect to submit
            context["all_answered"] = True

        return context

    def _get_prerequisite_questions(self, current_question, subject, limit=5):
        """
        Find questions that could serve as prerequisites for the current question.

        Looks for questions in the same subject with:
        1. Overlapping tags (related topics)
        2. Lower or equal difficulty (foundational knowledge)
        3. Filters out semantically similar/duplicate questions
        """
        from django.db.models import Case, IntegerField, Value, When

        current_tags = set(current_question.tags or [])
        if not current_tags:
            return []

        # Difficulty ordering: beginner=1, intermediate=2, advanced=3
        difficulty_order = Case(
            When(difficulty="beginner", then=Value(1)),
            When(difficulty="intermediate", then=Value(2)),
            When(difficulty="advanced", then=Value(3)),
            default=Value(2),
            output_field=IntegerField(),
        )

        # Get current question's difficulty level
        current_difficulty_level = {
            "beginner": 1,
            "intermediate": 2,
            "advanced": 3,
        }.get(current_question.difficulty, 2)

        # Find questions from same subject, excluding current question
        candidates = (
            Question.objects.filter(
                subject=subject,
                is_active=True,
            )
            .exclude(id=current_question.id)
            .annotate(difficulty_level=difficulty_order)
            .filter(difficulty_level__lte=current_difficulty_level)
            .order_by("difficulty_level")
        )

        # Score by tag overlap and select top matches
        scored_questions = []
        for q in candidates[:50]:  # Limit initial candidates for performance
            q_tags = set(q.tags or [])
            overlap = len(current_tags & q_tags)
            if overlap > 0:
                scored_questions.append((overlap, q))

        # Sort by overlap score (descending)
        scored_questions.sort(key=lambda x: -x[0])

        # Deduplicate similar questions
        result = []
        seen_normalized = set()

        for _, q in scored_questions:
            # Normalize question text for comparison
            normalized = self._normalize_question_text(q.question_text)

            # Check if we've seen a similar question
            is_duplicate = False
            for seen in seen_normalized:
                if self._is_similar(normalized, seen):
                    is_duplicate = True
                    break

            if not is_duplicate:
                seen_normalized.add(normalized)
                result.append(q)

            if len(result) >= limit:
                break

        return result

    def _normalize_question_text(self, text):
        """Normalize question text for similarity comparison."""
        import re
        # Lowercase, remove punctuation, collapse whitespace
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _is_similar(self, text1, text2, threshold=0.6):
        """Check if two normalized texts are similar using word overlap."""
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return False

        # Calculate Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)

        if union == 0:
            return False

        similarity = intersection / union

        # Also check if one is a subset of the other (catches rephrased questions)
        smaller = min(len(words1), len(words2))
        if smaller > 0 and intersection / smaller >= 0.8:
            return True

        return similarity >= threshold


@login_required
@require_POST
def submit_answer(request, subject_slug, pk):
    """Submit an answer to the current question."""
    session = get_object_or_404(
        ExamSession,
        pk=pk,
        user=request.user,
        status=ExamSession.Status.IN_PROGRESS,
    )

    # Get current answer slot
    answers = list(session.answers.order_by("order"))
    if session.current_question_index >= len(answers):
        return redirect("exam:submit", subject_slug=subject_slug, pk=pk)

    current_answer = answers[session.current_question_index]

    # Update answer
    current_answer.user_answer = request.POST.get("answer", "")
    current_answer.is_flagged = request.POST.get("flag") == "on"
    current_answer.answered_at = timezone.now()

    # Check if correct
    current_answer.check_answer()
    current_answer.save()

    # Update session
    session.current_question_index += 1
    session.total_answered += 1
    if current_answer.is_correct:
        session.score += 1
    session.save()

    # Check if exam is complete
    if session.current_question_index >= session.question_count:
        return redirect("exam:submit", subject_slug=subject_slug, pk=pk)

    return redirect("exam:question", subject_slug=subject_slug, pk=pk)


@login_required
@require_POST
def toggle_flag(request, subject_slug, pk):
    """Toggle the flag status on the current question."""
    session = get_object_or_404(
        ExamSession,
        pk=pk,
        user=request.user,
        status=ExamSession.Status.IN_PROGRESS,
    )

    answers = list(session.answers.order_by("order"))
    if session.current_question_index < len(answers):
        current_answer = answers[session.current_question_index]
        current_answer.is_flagged = not current_answer.is_flagged
        current_answer.save()

    return redirect("exam:question", subject_slug=subject_slug, pk=pk)


class ExamSubmitView(LoginRequiredMixin, DetailView):
    """Confirmation page before submitting the exam."""

    model = ExamSession
    template_name = "exam/submit.html"
    context_object_name = "session"

    def get_queryset(self):
        return ExamSession.objects.filter(
            user=self.request.user,
            status=ExamSession.Status.IN_PROGRESS,
        ).select_related("subject")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object
        answers = session.answers.select_related("question").order_by("order")

        context["answers"] = answers
        context["flagged_count"] = answers.filter(is_flagged=True).count()
        context["unanswered_count"] = answers.filter(user_answer="").count()

        return context


@login_required
@require_POST
def complete_exam(request, subject_slug, pk):
    """Complete the exam and calculate final score."""
    session = get_object_or_404(
        ExamSession,
        pk=pk,
        user=request.user,
        status=ExamSession.Status.IN_PROGRESS,
    )

    # Mark as completed
    session.status = ExamSession.Status.COMPLETED
    session.completed_at = timezone.now()
    session.save()

    messages.success(request, _("Exam completed! Review your results below."))
    return redirect("exam:results", subject_slug=subject_slug, pk=pk)


class ExamResultsView(LoginRequiredMixin, DetailView):
    """Display exam results and review."""

    model = ExamSession
    template_name = "exam/results.html"
    context_object_name = "session"

    def get_queryset(self):
        return ExamSession.objects.filter(
            user=self.request.user,
            status=ExamSession.Status.COMPLETED,
        ).select_related("subject")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object
        answers = session.answers.select_related("question").order_by("order")

        context["answers"] = answers
        context["correct_count"] = answers.filter(is_correct=True).count()
        context["incorrect_count"] = answers.filter(is_correct=False).count()
        context["flagged_answers"] = answers.filter(is_flagged=True)

        return context


@login_required
@require_POST
def create_llm_questions(request, subject_slug, pk, question_id):
    """
    Generate new Q&A questions from user's follow-up questions about an exam question.

    Uses the current exam question as context and generates answers to the user's
    questions, saving them as new Question records in the database.
    """
    from django.http import HttpResponse

    from apps.core.services.llm_service import LLMAPIError, get_llm_service
    from apps.questions.models import Question

    # Verify the session belongs to the user
    session = get_object_or_404(
        ExamSession,
        pk=pk,
        user=request.user,
    )

    # Get the original question for context
    original_question = get_object_or_404(Question, pk=question_id)

    # Parse user questions (each line starting with a hyphen is a separate question)
    user_questions_text = request.POST.get("user_questions", "").strip()
    if not user_questions_text:
        return HttpResponse(
            '<div class="text-red-600 text-sm">Please enter at least one question.</div>'
        )

    # Split by lines starting with hyphen, strip the hyphen and whitespace
    import re
    # Match lines that start with optional whitespace followed by a hyphen
    lines = user_questions_text.split("\n")
    user_questions = []
    current_question = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("-"):
            # Save previous question if exists
            if current_question:
                user_questions.append(" ".join(current_question))
            # Start new question (remove the leading hyphen)
            current_question = [stripped[1:].strip()]
        elif stripped and current_question:
            # Continuation of current question
            current_question.append(stripped)
        elif stripped and not current_question:
            # Line without hyphen and no current question - treat as standalone
            user_questions.append(stripped)

    # Don't forget the last question
    if current_question:
        user_questions.append(" ".join(current_question))

    # Filter out empty questions
    user_questions = [q.strip() for q in user_questions if q.strip()]

    if not user_questions:
        return HttpResponse(
            '<div class="text-red-600 text-sm">Please enter at least one question.</div>'
        )

    # Limit to 5 questions at a time
    if len(user_questions) > 5:
        user_questions = user_questions[:5]

    # Build the prompt for the LLM
    system_prompt = """You are an expert educator creating study questions and answers.
Given the context of an exam question and follow-up questions from a student,
provide clear, comprehensive answers that would help the student understand the topic better.

For each question, provide:
1. A clear, educational answer
2. Key points the student should remember

Respond with valid JSON only."""

    questions_list = "\n".join([f"{i+1}. {q}" for i, q in enumerate(user_questions)])

    prompt = f"""Context - Original Exam Question:
---
{original_question.question_text}

Correct Answer: {original_question.correct_answer}

Explanation: {original_question.explanation}
---

Subject Area: {session.subject.name}

Student's Follow-up Questions:
{questions_list}

For each question, provide a detailed answer. Respond with a JSON object:
{{
  "answers": [
    {{
      "question": "The student's question",
      "answer": "Your detailed answer",
      "key_points": ["point 1", "point 2"]
    }}
  ]
}}"""

    try:
        llm = get_llm_service()
        response = llm.generate_json_completion(
            prompt=prompt,
            system_message=system_prompt,
            max_tokens=4096,
            temperature=0.7,
        )

        answers_data = response.get("answers", [])
        saved_count = 0

        for item in answers_data:
            q_text = item.get("question", "")
            answer = item.get("answer", "")
            key_points = item.get("key_points", [])

            if q_text and answer:
                # Create a new free-text question
                import hashlib

                content = f"{session.subject.id}:{q_text}:{answer}"
                source_hash = hashlib.sha256(content.encode()).hexdigest()

                # Check for duplicates
                if not Question.objects.filter(source_hash=source_hash).exists():
                    # Build explanation with key points
                    explanation = answer
                    if key_points:
                        explanation += "\n\nKey Points:\n" + "\n".join(
                            [f"• {pt}" for pt in key_points]
                        )

                    Question.objects.create(
                        subject=session.subject,
                        question_text=q_text,
                        question_type=Question.QuestionType.FREE_TEXT,
                        correct_answer=answer,
                        explanation=explanation,
                        difficulty=original_question.difficulty,
                        tags=original_question.tags + ["user-generated", "follow-up"],
                        source=Question.Source.CLAUDE_API,
                        source_hash=source_hash,
                    )
                    saved_count += 1

        # Build HTML response showing the generated Q&A
        html_parts = []

        # Success header
        html_parts.append(
            f'<div class="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">'
            f'<div class="flex items-center">'
            f'<svg class="h-5 w-5 text-green-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
            f'<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>'
            f'</svg>'
            f'<span class="text-green-700 font-medium">Generated {len(answers_data)} answer(s)'
            f'{f", saved {saved_count} new question(s)" if saved_count > 0 else ""}</span>'
            f'</div>'
            f'</div>'
        )

        # Display each Q&A
        for i, item in enumerate(answers_data):
            q_text = item.get("question", "")
            answer = item.get("answer", "")
            key_points = item.get("key_points", [])

            html_parts.append(
                f'<div class="border border-gray-200 rounded-lg p-4 mb-3">'
                f'<div class="font-medium text-gray-900 mb-2">'
                f'<span class="text-purple-600">Q{i+1}:</span> {q_text}'
                f'</div>'
                f'<div class="text-gray-700 text-sm mb-2">'
                f'<span class="font-medium text-gray-900">Answer:</span> {answer}'
                f'</div>'
            )

            if key_points:
                html_parts.append('<div class="mt-2"><span class="text-xs font-medium text-gray-500">Key Points:</span><ul class="list-disc list-inside text-sm text-gray-600 mt-1">')
                for pt in key_points:
                    html_parts.append(f'<li>{pt}</li>')
                html_parts.append('</ul></div>')

            html_parts.append('</div>')

        if saved_count == 0 and len(answers_data) > 0:
            html_parts.append(
                '<div class="text-xs text-gray-500 mt-2">'
                'Note: Questions were not saved (they may already exist in the question bank).'
                '</div>'
            )

        return HttpResponse(''.join(html_parts))

    except LLMAPIError as e:
        logger.exception("Failed to generate LLM questions: %s", e)
        return HttpResponse(
            f'<div class="bg-red-50 border border-red-200 rounded-lg p-4">'
            f'<span class="text-red-700">Failed to generate questions: {str(e)}</span>'
            f'</div>'
        )
