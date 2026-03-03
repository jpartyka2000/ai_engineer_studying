"""Models for the questions app."""

import hashlib

from django.db import models
from django.utils.translation import gettext_lazy as _


class Question(models.Model):
    """
    Represents an exam question generated from source material or Claude API.

    Questions can be multiple choice (mc) or free text (free).
    They are cached in the database to minimize redundant API calls.
    """

    class QuestionType(models.TextChoices):
        MULTIPLE_CHOICE = "mc", _("Multiple Choice")
        FREE_TEXT = "free", _("Free Text")

    class Difficulty(models.TextChoices):
        BEGINNER = "beginner", _("Beginner")
        INTERMEDIATE = "intermediate", _("Intermediate")
        ADVANCED = "advanced", _("Advanced")

    class Source(models.TextChoices):
        LLM_STUDYING = "llm_studying", _("LLM Studying Files")
        CLAUDE_API = "claude_api", _("Claude API Generated")
        MANUAL = "manual", _("Manually Created")

    # Relationship
    subject = models.ForeignKey(
        "subjects.Subject",
        on_delete=models.CASCADE,
        related_name="questions",
        help_text=_("The subject area this question belongs to"),
    )

    # Question content
    question_text = models.TextField(
        help_text=_("The question text (may include code snippets)"),
    )
    question_type = models.CharField(
        max_length=10,
        choices=QuestionType.choices,
        default=QuestionType.MULTIPLE_CHOICE,
        help_text=_("Type of question: multiple choice or free text"),
    )
    options = models.JSONField(
        default=list,
        blank=True,
        help_text=_("List of answer options for multiple choice questions"),
    )
    correct_answer = models.TextField(
        help_text=_("The correct answer (option letter for MC, full text for free)"),
    )
    explanation = models.TextField(
        blank=True,
        help_text=_("Explanation of why the answer is correct"),
    )

    # Metadata
    difficulty = models.CharField(
        max_length=20,
        choices=Difficulty.choices,
        default=Difficulty.INTERMEDIATE,
        db_index=True,
        help_text=_("Difficulty level of the question"),
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Tags for categorizing the question"),
    )

    # Source tracking
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.CLAUDE_API,
        db_index=True,
        help_text=_("Where this question originated from"),
    )
    source_file = models.CharField(
        max_length=500,
        blank=True,
        help_text=_("Path to source file (for llm_studying questions)"),
    )
    source_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_("Hash of source content for deduplication"),
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text=_("Whether this question is available for use"),
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Question")
        verbose_name_plural = _("Questions")
        indexes = [
            models.Index(fields=["subject", "difficulty", "is_active"]),
            models.Index(fields=["subject", "question_type", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.subject.name}: {self.question_text[:50]}..."

    def save(self, *args, **kwargs) -> None:
        """Generate source hash if not provided."""
        if not self.source_hash and self.question_text:
            content = f"{self.subject_id}:{self.question_text}:{self.correct_answer}"
            self.source_hash = hashlib.sha256(content.encode()).hexdigest()
        super().save(*args, **kwargs)

    @property
    def is_multiple_choice(self) -> bool:
        """Check if this is a multiple choice question."""
        return self.question_type == self.QuestionType.MULTIPLE_CHOICE

    @property
    def options_list(self) -> list[dict]:
        """Return options as a list of dicts with letter and text."""
        if not self.options:
            return []
        letters = "ABCDEFGHIJ"
        return [
            {"letter": letters[i], "text": opt}
            for i, opt in enumerate(self.options)
            if i < len(letters)
        ]
