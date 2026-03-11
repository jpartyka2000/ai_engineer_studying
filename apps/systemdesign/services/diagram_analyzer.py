"""Service for analyzing system design diagrams using vision API."""

import base64
import logging
import tempfile
from pathlib import Path
from typing import Any

from apps.core.services.llm_service import LLMAPIError, get_llm_service
from apps.systemdesign.models import DiagramAnalysis, SystemDesignSession

logger = logging.getLogger(__name__)


class DiagramAnalyzer:
    """Service for analyzing system design diagrams using vision API."""

    ANALYSIS_PROMPT_TEMPLATE = """Analyze this system design diagram for the challenge: "{challenge_title}"

## Requirements the design should address:

### Functional Requirements:
{functional_requirements}

### Non-Functional Requirements:
{non_functional_requirements}

### Constraints:
{constraints}

## Your Task:
Analyze the diagram and identify:

1. **Components**: What system components can you see? (e.g., load balancers, databases, caches, services, queues, CDN, etc.)

2. **Connections**: What data flows or connections exist between components?

3. **Strengths**: What does this design do well?

4. **Concerns**: What potential issues or missing elements do you see?

5. **Suggestions**: What improvements would you recommend?

6. **Preliminary Scores** (1-10 scale):
   - Scalability: Can this design handle increased load?
   - Reliability: Is the system fault-tolerant?
   - Performance: Will it be fast/responsive?
   - Cost: Is it cost-effective (not over-engineered)?

Respond with JSON:
{{
    "identified_components": ["component1", "component2", ...],
    "identified_connections": [
        {{"from": "component1", "to": "component2", "description": "data flow description"}},
        ...
    ],
    "strengths": ["strength1", "strength2", ...],
    "concerns": ["concern1", "concern2", ...],
    "suggestions": ["suggestion1", "suggestion2", ...],
    "overall_impression": "Brief 1-2 sentence summary of the design",
    "preliminary_scores": {{
        "scalability": 7,
        "reliability": 6,
        "performance": 8,
        "cost": 7
    }}
}}

If the diagram is empty or unreadable, return appropriate empty arrays and low scores with an explanation in overall_impression."""

    def __init__(self, provider: str | None = None) -> None:
        """Initialize the diagram analyzer."""
        self.llm = get_llm_service(provider)

    def analyze_canvas(
        self,
        session: SystemDesignSession,
        png_data: bytes,
        canvas_json: dict | None = None,
        analysis_type: str = DiagramAnalysis.AnalysisType.ON_DEMAND,
    ) -> DiagramAnalysis:
        """
        Analyze the current canvas state using vision API.

        Args:
            session: The current session.
            png_data: PNG image data of the canvas.
            canvas_json: Optional Fabric.js JSON state for storage.
            analysis_type: Type of analysis (periodic, on_demand, final).

        Returns:
            DiagramAnalysis instance with results.

        Raises:
            LLMAPIError: If the vision API call fails.
        """
        prompt = self._build_analysis_prompt(session)

        try:
            # Write PNG to temp file for the vision API
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(png_data)
                temp_path = Path(f.name)

            try:
                response = self.llm.generate_vision_json_completion(
                    image_path=temp_path,
                    prompt=prompt,
                    system_message="You are an expert system design reviewer. Analyze diagrams thoroughly but constructively.",
                    max_tokens=2048,
                    temperature=0.3,  # Lower temperature for more consistent analysis
                )
            finally:
                # Clean up temp file
                temp_path.unlink(missing_ok=True)

            # Parse and validate response
            analysis_data = self._parse_analysis_response(response)

            # Create analysis record
            analysis = DiagramAnalysis.objects.create(
                session=session,
                analysis_type=analysis_type,
                canvas_state_snapshot=canvas_json or {},
                canvas_png_snapshot=png_data,
                identified_components=analysis_data.get("identified_components", []),
                identified_connections=analysis_data.get("identified_connections", []),
                strengths=analysis_data.get("strengths", []),
                concerns=analysis_data.get("concerns", []),
                suggestions=analysis_data.get("suggestions", []),
                overall_impression=analysis_data.get("overall_impression", ""),
                preliminary_scores=analysis_data.get("preliminary_scores", {}),
                raw_response=response,
            )

            # Update session's last analysis timestamp
            from django.utils import timezone
            session.last_analysis_at = timezone.now()
            session.save(update_fields=["last_analysis_at"])

            return analysis

        except Exception as e:
            logger.exception("Failed to analyze diagram: %s", str(e))
            raise LLMAPIError(f"Diagram analysis failed: {e}") from e

    def _build_analysis_prompt(self, session: SystemDesignSession) -> str:
        """Build the analysis prompt with challenge context."""
        fr = "\n".join(f"- {r}" for r in session.effective_functional_requirements) or "Not specified"
        nfr = "\n".join(f"- {r}" for r in session.effective_non_functional_requirements) or "Not specified"
        constraints = "\n".join(f"- {c}" for c in session.effective_constraints) or "Not specified"

        return self.ANALYSIS_PROMPT_TEMPLATE.format(
            challenge_title=session.effective_challenge_title,
            functional_requirements=fr,
            non_functional_requirements=nfr,
            constraints=constraints,
        )

    def _parse_analysis_response(self, response: dict[str, Any]) -> dict[str, Any]:
        """
        Parse and validate the analysis response.

        Handles various response formats and provides defaults for missing fields.
        """
        # Ensure all expected fields exist with proper types
        return {
            "identified_components": response.get("identified_components", []) or [],
            "identified_connections": response.get("identified_connections", []) or [],
            "strengths": response.get("strengths", []) or [],
            "concerns": response.get("concerns", []) or [],
            "suggestions": response.get("suggestions", []) or [],
            "overall_impression": response.get("overall_impression", "") or "",
            "preliminary_scores": self._normalize_scores(
                response.get("preliminary_scores", {})
            ),
        }

    def _normalize_scores(self, scores: dict | None) -> dict[str, int]:
        """Normalize scores to integers in 1-10 range."""
        if not scores:
            return {
                "scalability": 5,
                "reliability": 5,
                "performance": 5,
                "cost": 5,
            }

        normalized = {}
        for key in ["scalability", "reliability", "performance", "cost"]:
            value = scores.get(key, 5)
            if isinstance(value, (int, float)):
                normalized[key] = max(1, min(10, int(value)))
            else:
                normalized[key] = 5

        return normalized

    def should_auto_analyze(self, session: SystemDesignSession) -> bool:
        """
        Check if enough time has passed for automatic analysis.

        Auto-analysis occurs every 5 minutes.

        Args:
            session: The current session.

        Returns:
            True if auto-analysis should be triggered.
        """
        from django.utils import timezone
        from datetime import timedelta

        # Don't analyze if session is not in progress
        if session.status != session.Status.IN_PROGRESS:
            return False

        # Don't analyze if less than 2 minutes into the session
        elapsed = (timezone.now() - session.started_at).total_seconds()
        if elapsed < 120:
            return False

        # Check if 5 minutes have passed since last analysis
        if session.last_analysis_at:
            since_last = (timezone.now() - session.last_analysis_at).total_seconds()
            return since_last >= 300  # 5 minutes

        # First analysis after at least 2 minutes
        return True


# Singleton instance
_diagram_analyzer: DiagramAnalyzer | None = None


def get_diagram_analyzer(provider: str | None = None) -> DiagramAnalyzer:
    """Get the diagram analyzer singleton."""
    global _diagram_analyzer
    if _diagram_analyzer is None:
        _diagram_analyzer = DiagramAnalyzer(provider)
    return _diagram_analyzer
