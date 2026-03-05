"""Service for evaluating code submissions using Claude API."""

import logging

from django.utils import timezone

from apps.coding.models import CodingChallenge, CodingResponse, CodingSession
from apps.coding.schemas import CodeEvaluation
from apps.core.services.claude_service import ClaudeAPIError, get_claude_service

logger = logging.getLogger(__name__)


class CodeEvaluatorService:
    """
    Service for evaluating user code submissions using Claude.

    Provides comprehensive feedback on correctness, style,
    completeness, and efficiency without executing code.
    """

    SYSTEM_PROMPT = """You are an expert code reviewer evaluating submissions for a coding challenge.
Your role is to provide thorough, constructive feedback that helps the learner improve.

Evaluation Guidelines:
1. CORRECTNESS (0-100): Does the code solve the problem correctly?
   - Check logic flow and algorithm correctness
   - Verify edge case handling
   - Assess error handling

2. STYLE (0-100): Does the code follow best practices?
   - Variable/function naming conventions
   - Code organization and structure
   - Comments and documentation
   - Language-specific idioms

3. COMPLETENESS (0-100): Is the solution complete?
   - All requirements addressed
   - Input validation
   - Proper output formatting

4. EFFICIENCY (0-100): Is the code reasonably efficient?
   - Appropriate data structures
   - Algorithmic complexity
   - Avoid unnecessary operations

Feedback Guidelines:
- Be encouraging but honest
- Reference specific line numbers when pointing out issues
- Explain WHY something is good or bad
- Provide concrete suggestions for improvement
- Acknowledge creative or clever solutions

You must respond with valid JSON only."""

    SHELL_SYSTEM_PROMPT = """You are an expert Linux/Shell instructor evaluating shell command submissions.
Your role is to provide thorough, constructive feedback that helps the learner master shell scripting.

Evaluation Guidelines:
1. CORRECTNESS (0-100): Do the commands achieve the desired outcome?
   - Will the commands actually solve the problem?
   - Are the commands syntactically correct?
   - Are there any commands that would cause errors?

2. STYLE (0-100): Are the commands following shell best practices?
   - Using appropriate flags and options
   - Proper quoting and escaping
   - Following shell scripting conventions

3. COMPLETENESS (0-100): Is the solution complete?
   - All required steps included
   - Handles the scenario fully
   - No missing commands or logic

4. EFFICIENCY (0-100): Is this the optimal approach?
   - Minimal number of commands needed
   - Using the right tools for the task
   - Avoiding unnecessary operations or subshells

Feedback Guidelines:
- Be encouraging but honest
- Explain what each command does and why it's right or wrong
- Suggest alternative approaches if applicable
- Explain potential pitfalls (e.g., handling spaces in filenames)
- Reference specific commands in your feedback

You must respond with valid JSON only."""

    DOCKER_SYSTEM_PROMPT = """You are an expert Docker instructor evaluating Docker submissions.
Your role is to provide thorough, constructive feedback that helps the learner master Docker.

Evaluation Guidelines:
1. CORRECTNESS (0-100): Does the Dockerfile/config achieve the desired outcome?
   - Will it build successfully?
   - Will the container run as expected?
   - Are there any syntax errors?

2. STYLE (0-100): Are Docker best practices followed?
   - Layer ordering and caching optimization
   - Using appropriate base images
   - Following Dockerfile conventions
   - Proper use of .dockerignore patterns

3. COMPLETENESS (0-100): Is the solution complete?
   - All required functionality included
   - Proper exposure of ports
   - Correct volume mounts and environment variables

4. EFFICIENCY (0-100): Is this the optimal approach?
   - Image size optimization
   - Multi-stage builds where appropriate
   - Minimizing layers
   - Security considerations (non-root user, etc.)

Feedback Guidelines:
- Be encouraging but honest
- Explain what each instruction does and why it's right or wrong
- Suggest alternative approaches if applicable
- Highlight security and performance considerations
- Reference specific lines in your feedback

You must respond with valid JSON only."""

    GIT_SYSTEM_PROMPT = """You are an expert Git instructor evaluating Git command submissions.
Your role is to provide thorough, constructive feedback that helps the learner master Git.

Evaluation Guidelines:
1. CORRECTNESS (0-100): Do the commands achieve the desired outcome?
   - Will the commands actually solve the problem?
   - Are the commands in the right order?
   - Are there any commands that would cause errors?

2. STYLE (0-100): Are the commands following Git best practices?
   - Using appropriate flags and options
   - Clear commit messages (if applicable)
   - Following conventional Git workflows

3. COMPLETENESS (0-100): Is the solution complete?
   - All required steps included
   - Handles the scenario fully
   - No missing commands

4. EFFICIENCY (0-100): Is this the optimal approach?
   - Minimal number of commands needed
   - Using the right Git commands for the task
   - Avoiding unnecessary steps

Feedback Guidelines:
- Be encouraging but honest
- Explain what each command does and why it's right or wrong
- Suggest alternative approaches if applicable
- Explain potential pitfalls or edge cases
- Reference specific commands in your feedback

You must respond with valid JSON only."""

    def __init__(self) -> None:
        """Initialize the code evaluator service."""
        self.claude = get_claude_service()

    def evaluate_submission(
        self,
        session: CodingSession,
        submitted_code: str,
    ) -> CodingResponse:
        """
        Evaluate a code submission and create a CodingResponse.

        Args:
            session: The coding session.
            submitted_code: The user's submitted code.

        Returns:
            A CodingResponse with the evaluation results.
        """
        challenge = session.challenge

        # Use specialized evaluation for command-line challenges
        is_git = challenge.language == "git"
        is_shell = challenge.language == "shell"
        is_docker = challenge.language == "docker"

        # Build evaluation prompt based on language
        if is_git:
            prompt = self._build_git_evaluation_prompt(challenge, submitted_code)
            system_prompt = self.GIT_SYSTEM_PROMPT
        elif is_shell:
            prompt = self._build_shell_evaluation_prompt(challenge, submitted_code)
            system_prompt = self.SHELL_SYSTEM_PROMPT
        elif is_docker:
            prompt = self._build_docker_evaluation_prompt(challenge, submitted_code)
            system_prompt = self.DOCKER_SYSTEM_PROMPT
        else:
            prompt = self._build_evaluation_prompt(challenge, submitted_code)
            system_prompt = self.SYSTEM_PROMPT

        try:
            response = self.claude.generate_json_completion(
                prompt=prompt,
                system_message=system_prompt,
                max_tokens=4096,
                temperature=0.3,  # Lower temperature for more consistent evaluation
            )

            evaluation = CodeEvaluation.model_validate(response)

            # Determine submission number
            submission_count = session.responses.count()

            # Create response record
            coding_response = CodingResponse.objects.create(
                session=session,
                submitted_code=submitted_code,
                submission_number=submission_count + 1,
                is_correct=evaluation.is_correct,
                overall_score=evaluation.overall_score,
                evaluation_result=response,  # Store full JSON
                correctness_score=evaluation.correctness.score,
                style_score=evaluation.style.score,
                completeness_score=evaluation.completeness.score,
                efficiency_score=evaluation.efficiency.score,
                summary_feedback=evaluation.summary_feedback,
                detailed_feedback=evaluation.detailed_feedback,
                areas_for_improvement=evaluation.areas_for_improvement,
                strengths=evaluation.strengths,
                evaluated_at=timezone.now(),
            )

            return coding_response

        except ClaudeAPIError:
            raise
        except Exception as e:
            logger.exception("Failed to evaluate code: %s", str(e))
            raise ClaudeAPIError(f"Code evaluation failed: {e}") from e

    def _build_evaluation_prompt(
        self,
        challenge: CodingChallenge,
        submitted_code: str,
    ) -> str:
        """Build the evaluation prompt for Claude."""
        modify_context = ""
        if challenge.challenge_type == CodingChallenge.ChallengeType.MODIFY:
            modify_context = f"""
ORIGINAL CODE (with issues to fix):
```{challenge.language}
{challenge.starter_code}
```

The user was asked to fix/improve this code.
"""

        reference_context = ""
        if challenge.reference_solution:
            reference_context = f"""
REFERENCE SOLUTION (for comparison, not to be shared with user):
```{challenge.language}
{challenge.reference_solution}
```
"""

        criteria_list = "\n".join(f"- {c}" for c in challenge.evaluation_criteria)

        return f"""Evaluate this code submission for the following challenge:

CHALLENGE: {challenge.title}
TYPE: {challenge.challenge_type}
DIFFICULTY: {challenge.difficulty}
LANGUAGE: {challenge.language}

PROBLEM DESCRIPTION:
{challenge.description}

EXPECTED BEHAVIOR:
{challenge.expected_output}

EVALUATION CRITERIA:
{criteria_list}
{modify_context}
{reference_context}
USER'S SUBMITTED CODE:
```{challenge.language}
{submitted_code}
```

Provide a comprehensive evaluation as JSON with:
- is_correct: boolean (does it solve the problem?)
- overall_score: int 0-100
- correctness: {{"score": int, "feedback": str}}
- style: {{"score": int, "feedback": str}}
- completeness: {{"score": int, "feedback": str}}
- efficiency: {{"score": int, "feedback": str}}
- summary_feedback: Brief overall assessment
- detailed_feedback: Detailed review with line references
- areas_for_improvement: Array of specific suggestions
- strengths: Array of things done well"""

    def _build_git_evaluation_prompt(
        self,
        challenge: CodingChallenge,
        submitted_commands: str,
    ) -> str:
        """Build the evaluation prompt for Git command challenges."""
        scenario_context = ""
        if challenge.challenge_type == CodingChallenge.ChallengeType.MODIFY:
            scenario_context = f"""
INITIAL GIT STATE (the problematic situation):
```
{challenge.starter_code}
```

The user was asked to fix this Git state.
"""

        reference_context = ""
        if challenge.reference_solution:
            reference_context = f"""
REFERENCE SOLUTION (correct Git commands):
```bash
{challenge.reference_solution}
```
"""

        criteria_list = "\n".join(f"- {c}" for c in challenge.evaluation_criteria)

        return f"""Evaluate this Git command submission for the following challenge:

CHALLENGE: {challenge.title}
TYPE: {challenge.challenge_type}
DIFFICULTY: {challenge.difficulty}

SCENARIO:
{challenge.description}

EXPECTED OUTCOME:
{challenge.expected_output}

EVALUATION CRITERIA:
{criteria_list}
{scenario_context}
{reference_context}
USER'S SUBMITTED GIT COMMANDS:
```bash
{submitted_commands}
```

Evaluate the Git commands the user provided. Consider:
- Will these commands achieve the desired outcome?
- Are they in the correct order?
- Are there any missing or unnecessary commands?
- Is this an efficient solution?

Provide a comprehensive evaluation as JSON with:
- is_correct: boolean (will these commands solve the problem?)
- overall_score: int 0-100
- correctness: {{"score": int, "feedback": str}} - Do the commands work?
- style: {{"score": int, "feedback": str}} - Are Git best practices followed?
- completeness: {{"score": int, "feedback": str}} - Are all steps included?
- efficiency: {{"score": int, "feedback": str}} - Is this the optimal approach?
- summary_feedback: Brief overall assessment
- detailed_feedback: Detailed review explaining each command
- areas_for_improvement: Array of specific suggestions
- strengths: Array of things done well"""

    def _build_shell_evaluation_prompt(
        self,
        challenge: CodingChallenge,
        submitted_commands: str,
    ) -> str:
        """Build the evaluation prompt for Shell/Bash command challenges."""
        scenario_context = ""
        if challenge.challenge_type == CodingChallenge.ChallengeType.MODIFY:
            scenario_context = f"""
ORIGINAL SCRIPT/COMMANDS (with issues to fix):
```bash
{challenge.starter_code}
```

The user was asked to fix this script/commands.
"""

        reference_context = ""
        if challenge.reference_solution:
            reference_context = f"""
REFERENCE SOLUTION (correct shell commands):
```bash
{challenge.reference_solution}
```
"""

        criteria_list = "\n".join(f"- {c}" for c in challenge.evaluation_criteria)

        return f"""Evaluate this shell command submission for the following challenge:

CHALLENGE: {challenge.title}
TYPE: {challenge.challenge_type}
DIFFICULTY: {challenge.difficulty}

SCENARIO:
{challenge.description}

EXPECTED OUTCOME:
{challenge.expected_output}

EVALUATION CRITERIA:
{criteria_list}
{scenario_context}
{reference_context}
USER'S SUBMITTED SHELL COMMANDS:
```bash
{submitted_commands}
```

Evaluate the shell commands/script the user provided. Consider:
- Will these commands achieve the desired outcome?
- Are they syntactically correct?
- Are there any edge cases not handled (e.g., spaces in filenames)?
- Is this an efficient solution?

Provide a comprehensive evaluation as JSON with:
- is_correct: boolean (will these commands solve the problem?)
- overall_score: int 0-100
- correctness: {{"score": int, "feedback": str}} - Do the commands work?
- style: {{"score": int, "feedback": str}} - Are shell best practices followed?
- completeness: {{"score": int, "feedback": str}} - Are all steps included?
- efficiency: {{"score": int, "feedback": str}} - Is this the optimal approach?
- summary_feedback: Brief overall assessment
- detailed_feedback: Detailed review explaining each command
- areas_for_improvement: Array of specific suggestions
- strengths: Array of things done well"""

    def _build_docker_evaluation_prompt(
        self,
        challenge: CodingChallenge,
        submitted_code: str,
    ) -> str:
        """Build the evaluation prompt for Docker challenges."""
        scenario_context = ""
        if challenge.challenge_type == CodingChallenge.ChallengeType.MODIFY:
            scenario_context = f"""
ORIGINAL DOCKERFILE/CONFIG (with issues to fix):
```dockerfile
{challenge.starter_code}
```

The user was asked to fix this Docker configuration.
"""

        reference_context = ""
        if challenge.reference_solution:
            reference_context = f"""
REFERENCE SOLUTION:
```dockerfile
{challenge.reference_solution}
```
"""

        criteria_list = "\n".join(f"- {c}" for c in challenge.evaluation_criteria)

        return f"""Evaluate this Docker submission for the following challenge:

CHALLENGE: {challenge.title}
TYPE: {challenge.challenge_type}
DIFFICULTY: {challenge.difficulty}

SCENARIO:
{challenge.description}

EXPECTED OUTCOME:
{challenge.expected_output}

EVALUATION CRITERIA:
{criteria_list}
{scenario_context}
{reference_context}
USER'S SUBMITTED SOLUTION:
```dockerfile
{submitted_code}
```

Evaluate the Docker configuration the user provided. Consider:
- Will this build and run successfully?
- Does it follow Docker best practices?
- Is the image size optimized?
- Are there any security concerns?

Provide a comprehensive evaluation as JSON with:
- is_correct: boolean (will this achieve the goal?)
- overall_score: int 0-100
- correctness: {{"score": int, "feedback": str}} - Does it work?
- style: {{"score": int, "feedback": str}} - Are best practices followed?
- completeness: {{"score": int, "feedback": str}} - Is it complete?
- efficiency: {{"score": int, "feedback": str}} - Is it optimized?
- summary_feedback: Brief overall assessment
- detailed_feedback: Detailed review explaining each part
- areas_for_improvement: Array of specific suggestions
- strengths: Array of things done well"""


# Singleton
_evaluator: CodeEvaluatorService | None = None


def get_code_evaluator() -> CodeEvaluatorService:
    """Get the singleton code evaluator instance."""
    global _evaluator
    if _evaluator is None:
        _evaluator = CodeEvaluatorService()
    return _evaluator
