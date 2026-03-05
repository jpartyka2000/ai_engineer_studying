"""Service for generating coding challenges using Claude API."""

import hashlib
import logging
from typing import Literal

from apps.coding.models import CodingChallenge
from apps.coding.schemas import GeneratedChallenge, GeneratedChallengeSet
from apps.core.services.claude_service import ClaudeAPIError, get_claude_service
from apps.subjects.models import Subject

logger = logging.getLogger(__name__)


class ChallengeGeneratorService:
    """
    Service for generating coding challenges using Claude.

    Generates both 'implement from scratch' and 'modify existing code'
    challenges based on subject area and difficulty.
    """

    SYSTEM_PROMPT = """You are an expert coding challenge designer for technical interviews.
Your task is to create high-quality coding challenges that test practical programming skills.

Guidelines:
- Create challenges that test real coding ability, not trick questions
- For "implement" challenges: provide clear requirements and expected behavior
- For "modify" challenges: provide broken/incomplete code that needs fixing
- Include specific evaluation criteria that cover correctness, style, completeness
- Provide hints that guide without giving away the solution
- Reference solutions should follow best practices
- Difficulty should match the level appropriately:
  * Beginner: Basic syntax, simple algorithms, straightforward logic
  * Intermediate: Data structures, error handling, moderate complexity
  * Advanced: Optimization, edge cases, complex algorithms, system design

You must respond with valid JSON only."""

    GIT_SYSTEM_PROMPT = """You are an expert Git challenge designer for technical interviews.
Your task is to create realistic Git command-line scenarios that test practical Git skills.

Guidelines:
- Create scenarios that test real Git workflow abilities
- Present a realistic situation (merge conflict, rebasing, recovering commits, etc.)
- The user should respond with the exact Git commands they would run
- For "implement" challenges: describe a scenario where the user needs to achieve a goal
- For "modify" challenges: show a problematic Git state that needs to be fixed
- Include specific evaluation criteria for correct command usage
- Provide hints that guide without giving away the exact commands
- Reference solutions should show the optimal sequence of Git commands

Difficulty levels:
  * Beginner: Basic commands (add, commit, push, pull, branch, checkout)
  * Intermediate: Merging, rebasing, stashing, cherry-pick, reset
  * Advanced: Interactive rebase, reflog recovery, complex merge strategies, hooks

You must respond with valid JSON only."""

    SHELL_SYSTEM_PROMPT = """You are an expert Linux/Shell challenge designer for technical interviews.
Your task is to create realistic shell scripting and command-line scenarios that test practical Linux skills.

Guidelines:
- Create scenarios that test real shell/bash abilities
- Present realistic situations (file manipulation, text processing, system administration, etc.)
- The user should respond with the exact shell commands or scripts they would run
- For "implement" challenges: describe a task the user needs to accomplish with shell commands
- For "modify" challenges: show a broken script or incorrect command that needs fixing
- Include specific evaluation criteria for correct command usage
- Provide hints that guide without giving away the exact commands
- Reference solutions should show the optimal commands or script

Difficulty levels:
  * Beginner: Basic commands (ls, cd, cp, mv, rm, cat, grep, echo, pipes)
  * Intermediate: sed, awk, find, xargs, process management, file permissions
  * Advanced: Complex scripting, regex, system administration, networking commands

You must respond with valid JSON only."""

    DOCKER_SYSTEM_PROMPT = """You are an expert Docker challenge designer for technical interviews.
Your task is to create realistic Docker scenarios that test practical containerization skills.

Guidelines:
- Create scenarios that test real Docker abilities
- Include Dockerfile writing, docker commands, and docker-compose
- The user should respond with Dockerfiles, docker commands, or docker-compose.yml content
- For "implement" challenges: describe a containerization goal the user needs to achieve
- For "modify" challenges: show a broken Dockerfile or docker-compose that needs fixing
- Include specific evaluation criteria for correct Docker usage
- Provide hints that guide without giving away the exact solution
- Reference solutions should show best practices for Docker

Difficulty levels:
  * Beginner: Basic Dockerfile (FROM, RUN, COPY, CMD), docker run, docker build
  * Intermediate: Multi-stage builds, docker-compose, volumes, networks, environment variables
  * Advanced: Optimization, security best practices, complex orchestration, health checks

You must respond with valid JSON only."""

    def __init__(self) -> None:
        """Initialize the challenge generator service."""
        self.claude = get_claude_service()

    def generate_challenges(
        self,
        subject: Subject,
        topic: str,
        num_challenges: int = 2,
        difficulty: str | None = None,
        challenge_type: Literal["implement", "modify", "both"] = "both",
        language: str = "python",
    ) -> list[GeneratedChallenge]:
        """
        Generate coding challenges for a subject and topic.

        Args:
            subject: The subject area.
            topic: Specific topic within the subject.
            num_challenges: Number of challenges to generate.
            difficulty: Target difficulty level.
            challenge_type: Type of challenges to generate.
            language: Programming language.

        Returns:
            List of generated challenges.
        """
        # Use specialized generation for command-line challenges
        if language == "git":
            return self._generate_git_challenges(
                subject, topic, num_challenges, difficulty, challenge_type
            )
        if language == "shell":
            return self._generate_shell_challenges(
                subject, topic, num_challenges, difficulty, challenge_type
            )
        if language == "docker":
            return self._generate_docker_challenges(
                subject, topic, num_challenges, difficulty, challenge_type
            )

        type_instruction = {
            "implement": "All challenges should be 'implement from scratch' type.",
            "modify": (
                "All challenges should be 'modify existing code' type with starter "
                "code that has bugs or is incomplete."
            ),
            "both": "Include a mix of 'implement' and 'modify' challenges.",
        }[challenge_type]

        difficulty_instruction = (
            f"All challenges should be at '{difficulty}' difficulty level."
            if difficulty
            else "Vary difficulty levels appropriately."
        )

        prompt = f"""Generate {num_challenges} coding challenges about "{topic}"
in the subject area of "{subject.name}" using {language}.

Requirements:
- {type_instruction}
- {difficulty_instruction}
- Each challenge should test practical coding skills
- Include clear evaluation criteria (4-6 specific points)
- Provide 2-3 progressive hints
- Include a reference solution
- Estimate reasonable completion time

For 'modify' type challenges, provide starter code with intentional issues:
- Bugs to fix
- Missing error handling
- Incomplete implementations
- Style violations to correct

Respond with a JSON object containing a "challenges" array with these fields:
- title: Brief descriptive title
- description: Full problem statement with requirements (use markdown)
- challenge_type: "implement" or "modify"
- language: "{language}"
- starter_code: Initial code (empty string for implement, buggy/incomplete for modify)
- reference_solution: Working solution following best practices
- evaluation_criteria: Array of specific criteria to check
- expected_output: Description of expected behavior
- hints: Array of 2-3 progressive hints
- difficulty: "beginner", "intermediate", or "advanced"
- tags: Array of relevant topic tags
- estimated_time_minutes: Estimated completion time"""

        try:
            response = self.claude.generate_json_completion(
                prompt=prompt,
                system_message=self.SYSTEM_PROMPT,
                max_tokens=8192,
                temperature=0.7,
            )

            challenge_set = GeneratedChallengeSet.model_validate(response)
            return challenge_set.challenges

        except ClaudeAPIError:
            raise
        except Exception as e:
            logger.exception("Failed to generate challenges: %s", str(e))
            raise ClaudeAPIError(f"Challenge generation failed: {e}") from e

    def _generate_git_challenges(
        self,
        subject: Subject,
        topic: str,
        num_challenges: int,
        difficulty: str | None,
        challenge_type: Literal["implement", "modify", "both"],
    ) -> list[GeneratedChallenge]:
        """Generate Git command-line scenario challenges."""
        type_instruction = {
            "implement": (
                "All challenges should be 'implement' type where the user must "
                "write Git commands to achieve a goal from a described starting state."
            ),
            "modify": (
                "All challenges should be 'modify' type where the user is given "
                "a problematic Git state (shown in starter_code as terminal output) "
                "and must fix it with the correct Git commands."
            ),
            "both": "Include a mix of 'implement' and 'modify' challenges.",
        }[challenge_type]

        difficulty_instruction = (
            f"All challenges should be at '{difficulty}' difficulty level."
            if difficulty
            else "Vary difficulty levels appropriately."
        )

        prompt = f"""Generate {num_challenges} Git command-line challenges about "{topic}"
in the subject area of "{subject.name}".

Requirements:
- {type_instruction}
- {difficulty_instruction}
- Create realistic Git scenarios that developers encounter
- The user should respond with the exact Git commands they would type
- Include clear evaluation criteria (4-6 specific points)
- Provide 2-3 progressive hints
- Include the correct sequence of Git commands as the reference solution

For 'modify' type challenges, the starter_code should show:
- Current git status output
- git log output showing the problematic state
- Any relevant error messages
- Branch information

Respond with a JSON object containing a "challenges" array with these fields:
- title: Brief descriptive title (e.g., "Resolve a Merge Conflict", "Recover a Deleted Branch")
- description: Full scenario description with context (use markdown). Include:
  * The current situation/problem
  * What the user needs to accomplish
  * Any constraints (e.g., "without losing commits", "preserving history")
- challenge_type: "implement" or "modify"
- language: "git"
- starter_code: For modify challenges, show the terminal output/git state. For implement, can be empty or show initial repo state.
- reference_solution: The correct sequence of Git commands, one per line
- evaluation_criteria: Array of specific criteria (e.g., "Uses git rebase correctly", "Preserves commit history")
- expected_output: Description of the expected final Git state
- hints: Array of 2-3 progressive hints (e.g., "Consider using git reflog", "The -i flag allows interactive mode")
- difficulty: "beginner", "intermediate", or "advanced"
- tags: Array of relevant Git concept tags
- estimated_time_minutes: Estimated completion time (typically 5-15 for Git challenges)"""

        try:
            response = self.claude.generate_json_completion(
                prompt=prompt,
                system_message=self.GIT_SYSTEM_PROMPT,
                max_tokens=8192,
                temperature=0.7,
            )

            challenge_set = GeneratedChallengeSet.model_validate(response)
            return challenge_set.challenges

        except ClaudeAPIError:
            raise
        except Exception as e:
            logger.exception("Failed to generate Git challenges: %s", str(e))
            raise ClaudeAPIError(f"Git challenge generation failed: {e}") from e

    def _generate_shell_challenges(
        self,
        subject: Subject,
        topic: str,
        num_challenges: int,
        difficulty: str | None,
        challenge_type: Literal["implement", "modify", "both"],
    ) -> list[GeneratedChallenge]:
        """Generate Shell/Bash command-line scenario challenges."""
        type_instruction = {
            "implement": (
                "All challenges should be 'implement' type where the user must "
                "write shell commands or a bash script to achieve a goal."
            ),
            "modify": (
                "All challenges should be 'modify' type where the user is given "
                "a broken script or incorrect commands and must fix them."
            ),
            "both": "Include a mix of 'implement' and 'modify' challenges.",
        }[challenge_type]

        difficulty_instruction = (
            f"All challenges should be at '{difficulty}' difficulty level."
            if difficulty
            else "Vary difficulty levels appropriately."
        )

        prompt = f"""Generate {num_challenges} Shell/Bash command-line challenges about "{topic}"
in the subject area of "{subject.name}".

Requirements:
- {type_instruction}
- {difficulty_instruction}
- Create realistic shell scenarios that developers and sysadmins encounter
- The user should respond with the exact shell commands or script they would use
- Include clear evaluation criteria (4-6 specific points)
- Provide 2-3 progressive hints
- Include the correct commands or script as the reference solution

For 'modify' type challenges, the starter_code should show:
- The broken script or incorrect commands
- Any error messages that would be produced
- Expected vs actual behavior

Respond with a JSON object containing a "challenges" array with these fields:
- title: Brief descriptive title (e.g., "Find Large Files", "Process Log Files")
- description: Full scenario description with context (use markdown). Include:
  * The current situation/task
  * What the user needs to accomplish
  * Any constraints or requirements
- challenge_type: "implement" or "modify"
- language: "shell"
- starter_code: For modify challenges, show the broken script. For implement, can be empty or show sample data.
- reference_solution: The correct shell commands or script
- evaluation_criteria: Array of specific criteria (e.g., "Uses find command correctly", "Handles spaces in filenames")
- expected_output: Description of the expected result
- hints: Array of 2-3 progressive hints
- difficulty: "beginner", "intermediate", or "advanced"
- tags: Array of relevant shell/Linux concept tags
- estimated_time_minutes: Estimated completion time (typically 5-15 for shell challenges)"""

        try:
            response = self.claude.generate_json_completion(
                prompt=prompt,
                system_message=self.SHELL_SYSTEM_PROMPT,
                max_tokens=8192,
                temperature=0.7,
            )

            challenge_set = GeneratedChallengeSet.model_validate(response)
            return challenge_set.challenges

        except ClaudeAPIError:
            raise
        except Exception as e:
            logger.exception("Failed to generate shell challenges: %s", str(e))
            raise ClaudeAPIError(f"Shell challenge generation failed: {e}") from e

    def _generate_docker_challenges(
        self,
        subject: Subject,
        topic: str,
        num_challenges: int,
        difficulty: str | None,
        challenge_type: Literal["implement", "modify", "both"],
    ) -> list[GeneratedChallenge]:
        """Generate Docker scenario challenges."""
        type_instruction = {
            "implement": (
                "All challenges should be 'implement' type where the user must "
                "write a Dockerfile, docker commands, or docker-compose.yml to achieve a goal."
            ),
            "modify": (
                "All challenges should be 'modify' type where the user is given "
                "a broken or suboptimal Dockerfile/docker-compose and must fix it."
            ),
            "both": "Include a mix of 'implement' and 'modify' challenges.",
        }[challenge_type]

        difficulty_instruction = (
            f"All challenges should be at '{difficulty}' difficulty level."
            if difficulty
            else "Vary difficulty levels appropriately."
        )

        prompt = f"""Generate {num_challenges} Docker challenges about "{topic}"
in the subject area of "{subject.name}".

Requirements:
- {type_instruction}
- {difficulty_instruction}
- Create realistic Docker scenarios that developers encounter
- The user should respond with Dockerfiles, docker commands, or docker-compose.yml
- Include clear evaluation criteria (4-6 specific points)
- Provide 2-3 progressive hints
- Include the correct solution as the reference

For 'modify' type challenges, the starter_code should show:
- The broken or suboptimal Dockerfile/docker-compose
- Any error messages or issues
- What's wrong with the current approach

Respond with a JSON object containing a "challenges" array with these fields:
- title: Brief descriptive title (e.g., "Multi-Stage Build for Node.js", "Fix Docker Compose Networking")
- description: Full scenario description with context (use markdown). Include:
  * The current situation/goal
  * What the user needs to accomplish
  * Any constraints or requirements
- challenge_type: "implement" or "modify"
- language: "docker"
- starter_code: For modify challenges, show the broken config. For implement, can show context or be empty.
- reference_solution: The correct Dockerfile, commands, or docker-compose.yml
- evaluation_criteria: Array of specific criteria (e.g., "Uses multi-stage build", "Minimizes image size")
- expected_output: Description of the expected result
- hints: Array of 2-3 progressive hints
- difficulty: "beginner", "intermediate", or "advanced"
- tags: Array of relevant Docker concept tags
- estimated_time_minutes: Estimated completion time"""

        try:
            response = self.claude.generate_json_completion(
                prompt=prompt,
                system_message=self.DOCKER_SYSTEM_PROMPT,
                max_tokens=8192,
                temperature=0.7,
            )

            challenge_set = GeneratedChallengeSet.model_validate(response)
            return challenge_set.challenges

        except ClaudeAPIError:
            raise
        except Exception as e:
            logger.exception("Failed to generate Docker challenges: %s", str(e))
            raise ClaudeAPIError(f"Docker challenge generation failed: {e}") from e

    def save_challenges(
        self,
        challenges: list[GeneratedChallenge],
        subject: Subject,
    ) -> list[CodingChallenge]:
        """
        Save generated challenges to the database.

        Args:
            challenges: List of generated challenges.
            subject: The subject these challenges belong to.

        Returns:
            List of saved CodingChallenge instances.
        """
        saved = []

        for gen_c in challenges:
            # Generate hash for deduplication
            content = f"{subject.id}:{gen_c.title}:{gen_c.description[:200]}"
            source_hash = hashlib.sha256(content.encode()).hexdigest()

            # Check if exists
            if CodingChallenge.objects.filter(source_hash=source_hash).exists():
                logger.info("Challenge already exists: %s", gen_c.title)
                continue

            challenge = CodingChallenge.objects.create(
                subject=subject,
                title=gen_c.title,
                description=gen_c.description,
                challenge_type=gen_c.challenge_type,
                language=gen_c.language,
                starter_code=gen_c.starter_code,
                reference_solution=gen_c.reference_solution,
                evaluation_criteria=gen_c.evaluation_criteria,
                expected_output=gen_c.expected_output,
                hints=gen_c.hints,
                difficulty=gen_c.difficulty,
                tags=gen_c.tags,
                estimated_time_minutes=gen_c.estimated_time_minutes,
                source=CodingChallenge.Source.CLAUDE_API,
                source_hash=source_hash,
            )
            saved.append(challenge)
            logger.info("Saved challenge: %s", challenge.title)

        return saved


# Singleton
_generator: ChallengeGeneratorService | None = None


def get_challenge_generator() -> ChallengeGeneratorService:
    """Get the singleton challenge generator instance."""
    global _generator
    if _generator is None:
        _generator = ChallengeGeneratorService()
    return _generator
