"""Service for evaluating code submissions using Claude API and code execution."""

import logging

from django.utils import timezone

from apps.coding.models import (
    CodingChallenge,
    CodingResponse,
    CodingSession,
    ExecutionResult,
)
from apps.coding.schemas import CodeEvaluation
from apps.coding.services.code_runner import (
    CodeRunnerError,
    CodeRunnerService,
    TestResult,
    get_code_runner,
)
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
        self.code_runner = get_code_runner()

    def _run_test_cases(
        self,
        challenge: CodingChallenge,
        submitted_code: str,
        coding_response: CodingResponse,
    ) -> tuple[int, int, list[TestResult]]:
        """
        Run code against test cases and store results.

        Args:
            challenge: The coding challenge
            submitted_code: The user's submitted code
            coding_response: The CodingResponse to attach results to

        Returns:
            Tuple of (tests_passed, total_tests, test_results)
        """
        test_cases = list(challenge.test_cases.all())

        if not test_cases:
            return 0, 0, []

        try:
            results = self.code_runner.execute_all_tests(
                code=submitted_code,
                test_cases=test_cases,
            )
        except CodeRunnerError as e:
            logger.warning("Code runner error: %s", e)
            return 0, len(test_cases), []

        # Store execution results
        tests_passed = 0
        for result in results:
            # Map status to model choice
            status_map = {
                "passed": ExecutionResult.Status.PASSED,
                "failed": ExecutionResult.Status.FAILED,
                "error": ExecutionResult.Status.ERROR,
                "timeout": ExecutionResult.Status.TIMEOUT,
            }
            status = status_map.get(result.status, ExecutionResult.Status.ERROR)

            ExecutionResult.objects.create(
                response=coding_response,
                test_case_id=result.test_case_id,
                status=status,
                actual_output=result.actual_output,
                stdout=result.stdout,
                stderr=result.stderr,
                error_message=result.error_message,
                execution_time_ms=result.execution_time_ms,
            )

            if result.passed:
                tests_passed += 1

        return tests_passed, len(test_cases), results

    def _build_test_results_context(
        self,
        test_results: list[TestResult],
    ) -> str:
        """Build context string about test results for Claude."""
        if not test_results:
            return ""

        lines = ["\nTEST EXECUTION RESULTS:"]
        for result in test_results:
            status_emoji = "PASS" if result.passed else "FAIL"
            lines.append(f"- [{status_emoji}] {result.test_name}")
            if not result.passed:
                lines.append(f"  Expected: {result.expected_output}")
                lines.append(f"  Actual: {result.actual_output}")
                if result.error_message:
                    lines.append(f"  Error: {result.error_message}")

        return "\n".join(lines)

    def evaluate_submission(
        self,
        session: CodingSession,
        submitted_code: str,
        run_tests: bool = True,
    ) -> CodingResponse:
        """
        Evaluate a code submission using hybrid evaluation.

        For Python challenges with test cases:
        1. Run code against test cases in Docker
        2. If tests pass, get Claude feedback on style/efficiency
        3. If tests fail, still get Claude feedback but reflect test failures

        For other languages (git, shell, docker):
        - Use Claude-only evaluation

        Args:
            session: The coding session.
            submitted_code: The user's submitted code.
            run_tests: Whether to run test cases (default True).

        Returns:
            A CodingResponse with the evaluation results.
        """
        challenge = session.challenge

        # Determine submission number first
        submission_count = session.responses.count()

        # Check if this is a Python challenge with test cases
        is_python = challenge.language == "python"
        has_test_cases = challenge.test_cases.exists()
        should_run_tests = run_tests and is_python and has_test_cases

        # For hybrid evaluation, create the response first so we can attach test results
        if should_run_tests:
            # Create initial response record (will update after tests and Claude eval)
            coding_response = CodingResponse.objects.create(
                session=session,
                submitted_code=submitted_code,
                submission_number=submission_count + 1,
            )

            # Run test cases
            tests_passed, total_tests, test_results = self._run_test_cases(
                challenge, submitted_code, coding_response
            )

            # Build test results context for Claude
            test_context = self._build_test_results_context(test_results)

            # Calculate correctness based on tests
            if total_tests > 0:
                test_pass_rate = tests_passed / total_tests
                # If all tests pass, code is correct
                test_based_correctness = tests_passed == total_tests
            else:
                test_pass_rate = 0
                test_based_correctness = None

        else:
            coding_response = None
            test_context = ""
            test_based_correctness = None
            tests_passed = 0
            total_tests = 0

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
            prompt = self._build_evaluation_prompt(
                challenge, submitted_code, test_context
            )
            system_prompt = self.SYSTEM_PROMPT

        try:
            response = self.claude.generate_json_completion(
                prompt=prompt,
                system_message=system_prompt,
                max_tokens=4096,
                temperature=0.3,  # Lower temperature for more consistent evaluation
            )

            evaluation = CodeEvaluation.model_validate(response)

            # Determine final is_correct:
            # - If tests were run, use test results
            # - Otherwise, use Claude's assessment
            if test_based_correctness is not None:
                final_is_correct = test_based_correctness
                # Adjust correctness score based on test pass rate
                if total_tests > 0:
                    test_correctness_score = int((tests_passed / total_tests) * 100)
                    # Use the lower of test-based or Claude-based score
                    final_correctness_score = min(
                        test_correctness_score, evaluation.correctness.score
                    )
                else:
                    final_correctness_score = evaluation.correctness.score
            else:
                final_is_correct = evaluation.is_correct
                final_correctness_score = evaluation.correctness.score

            # Recalculate overall score if tests were run
            if total_tests > 0:
                # Weight: correctness 40%, style 20%, completeness 20%, efficiency 20%
                overall_score = int(
                    final_correctness_score * 0.4
                    + evaluation.style.score * 0.2
                    + evaluation.completeness.score * 0.2
                    + evaluation.efficiency.score * 0.2
                )
            else:
                overall_score = evaluation.overall_score

            # Update or create response record
            if coding_response:
                # Update existing response
                coding_response.is_correct = final_is_correct
                coding_response.overall_score = overall_score
                coding_response.evaluation_result = response
                coding_response.correctness_score = final_correctness_score
                coding_response.style_score = evaluation.style.score
                coding_response.completeness_score = evaluation.completeness.score
                coding_response.efficiency_score = evaluation.efficiency.score
                coding_response.summary_feedback = evaluation.summary_feedback
                coding_response.detailed_feedback = evaluation.detailed_feedback
                coding_response.areas_for_improvement = evaluation.areas_for_improvement
                coding_response.strengths = evaluation.strengths
                coding_response.evaluated_at = timezone.now()
                coding_response.save()
            else:
                # Create new response record
                coding_response = CodingResponse.objects.create(
                    session=session,
                    submitted_code=submitted_code,
                    submission_number=submission_count + 1,
                    is_correct=final_is_correct,
                    overall_score=overall_score,
                    evaluation_result=response,
                    correctness_score=final_correctness_score,
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
            # If Claude fails but we have test results, return partial evaluation
            if coding_response and total_tests > 0:
                coding_response.is_correct = test_based_correctness
                coding_response.overall_score = int(
                    (tests_passed / total_tests) * 100
                ) if total_tests > 0 else 0
                coding_response.correctness_score = coding_response.overall_score
                coding_response.summary_feedback = (
                    f"Tests: {tests_passed}/{total_tests} passed. "
                    "Claude evaluation unavailable."
                )
                coding_response.evaluated_at = timezone.now()
                coding_response.save()
                return coding_response
            raise
        except Exception as e:
            logger.exception("Failed to evaluate code: %s", str(e))
            raise ClaudeAPIError(f"Code evaluation failed: {e}") from e

    def _build_evaluation_prompt(
        self,
        challenge: CodingChallenge,
        submitted_code: str,
        test_context: str = "",
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

        # Add test results context if available
        test_section = ""
        if test_context:
            test_section = f"""
{test_context}

NOTE: The code has been executed against test cases. Use these results to inform
your CORRECTNESS score. Focus your feedback on STYLE and EFFICIENCY improvements.
"""

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
{test_section}
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
