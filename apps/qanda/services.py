"""Services for the qanda app."""

import logging
import re
from pathlib import Path

from django.conf import settings

from apps.core.services.claude_service import ClaudeAPIError, get_claude_service
from apps.questions.models import Question
from apps.questions.services.question_generator import get_question_generator
from apps.subjects.models import Subject

logger = logging.getLogger(__name__)


class TopicExtractionError(Exception):
    """Raised when topic extraction fails."""

    pass


class SaveTopicError(Exception):
    """Raised when saving topic fails."""

    pass


def extract_topic_name(content: str) -> str:
    """
    Extract a concise topic name from LLM response content using Claude.

    Args:
        content: The LLM response content to extract topic from.

    Returns:
        A snake_case topic name suitable for a filename.

    Raises:
        TopicExtractionError: If extraction fails.
    """
    claude = get_claude_service()

    # Limit content to avoid token waste
    truncated_content = content[:2000]

    prompt = f"""Analyze the following technical content and extract a concise topic name for it.
The topic name should:
- Be 2-5 words maximum
- Describe the main concept or technique covered
- Be in snake_case format (lowercase with underscores)
- Not include generic words like "about", "how_to", "understanding", "explanation"

Content:
---
{truncated_content}
---

Respond with JSON: {{"topic_name": "your_snake_case_name"}}"""

    try:
        response = claude.generate_json_completion(
            prompt=prompt,
            system_message="You extract concise topic names from technical content. Respond with valid JSON only.",
            max_tokens=100,
            temperature=0.3,
        )
        topic_name = response.get("topic_name", "")

        # Sanitize: ensure valid filename characters only
        topic_name = re.sub(r"[^a-z0-9_]", "_", topic_name.lower())
        topic_name = re.sub(r"_+", "_", topic_name).strip("_")

        if not topic_name:
            raise TopicExtractionError("Empty topic name extracted")

        return topic_name

    except ClaudeAPIError as e:
        logger.exception("Failed to extract topic name: %s", e)
        raise TopicExtractionError(f"Topic extraction failed: {e}") from e


def save_topic_file(
    content: str,
    subject: Subject,
    topic_name: str,
) -> Path:
    """
    Save content to an llm_studying file.

    Args:
        content: The content to save.
        subject: The subject this content belongs to.
        topic_name: The snake_case topic name for the filename.

    Returns:
        Path to the saved file.

    Raises:
        SaveTopicError: If saving fails.
    """
    # Build path: llm_studying/<subject_slug>/<topic_name>.txt
    llm_studying_dir = settings.BASE_DIR / "llm_studying"
    subject_dir = llm_studying_dir / subject.slug

    # Create directory if it doesn't exist
    try:
        subject_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise SaveTopicError(f"Failed to create directory {subject_dir}: {e}") from e

    # Generate unique filename if file exists
    file_path = subject_dir / f"{topic_name}.txt"
    if file_path.exists():
        counter = 1
        while file_path.exists():
            file_path = subject_dir / f"{topic_name}_{counter}.txt"
            counter += 1
            if counter > 100:  # Safety limit
                raise SaveTopicError(f"Too many files with name {topic_name}")

    # Write content
    try:
        file_path.write_text(content, encoding="utf-8")
        logger.info("Saved topic file: %s", file_path)
        return file_path
    except OSError as e:
        raise SaveTopicError(f"Failed to write file {file_path}: {e}") from e


def save_as_topic(
    content: str,
    subject: Subject,
    num_questions: int = 3,
) -> dict:
    """
    Complete save-as-topic workflow: extract name, save file, generate questions.

    Args:
        content: The LLM response content to save.
        subject: The subject this content belongs to.
        num_questions: Number of questions to generate.

    Returns:
        Dict with keys: topic_name, file_path, questions_created

    Raises:
        TopicExtractionError: If topic extraction fails.
        SaveTopicError: If file saving fails.
    """
    # Step 1: Extract topic name
    topic_name = extract_topic_name(content)

    # Step 2: Save file
    file_path = save_topic_file(content, subject, topic_name)

    # Step 3: Generate and save questions
    question_generator = get_question_generator()

    try:
        generated_questions = question_generator.generate_from_content(
            content=content,
            subject=subject,
            topic=topic_name.replace("_", " "),
            num_questions=num_questions,
        )

        saved_questions = question_generator.save_questions(
            questions=generated_questions,
            subject=subject,
            source=Question.Source.LLM_STUDYING,
            source_file=str(file_path),
        )
        questions_created = len(saved_questions)

    except Exception as e:
        logger.warning("Question generation failed (file still saved): %s", e)
        questions_created = 0

    return {
        "topic_name": topic_name,
        "file_path": str(file_path),
        "questions_created": questions_created,
    }
