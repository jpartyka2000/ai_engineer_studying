"""Service for executing Python code in Docker containers.

This service provides secure code execution for coding challenges by running
user-submitted code in isolated Docker containers with strict resource limits.
"""

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Result of executing a single test case."""

    test_case_id: int
    test_name: str
    passed: bool
    status: str  # passed, failed, error, timeout
    expected_output: object
    actual_output: object
    stdout: str
    stderr: str
    error_message: str
    execution_time_ms: int


@dataclass
class ExecutionOutput:
    """Output from running code in Docker."""

    success: bool
    return_value: object
    stdout: str
    stderr: str
    error: str
    error_type: str
    execution_time_ms: int


class CodeRunnerError(Exception):
    """Error during code execution."""

    pass


class DockerNotAvailableError(CodeRunnerError):
    """Docker is not available or not running."""

    pass


class CodeRunnerService:
    """
    Service for executing Python code against test cases in Docker containers.

    Security measures:
    - Network isolation: --network none
    - Memory limit: 128MB by default
    - CPU limit: 0.5 cores by default
    - Timeout: 5 seconds per test by default
    - Read-only filesystem: --read-only
    - Non-root user in container
    - Restricted Python imports (enforced by runner.py)
    """

    # Docker configuration
    DOCKER_IMAGE = "python-runner:latest"
    MEMORY_LIMIT = "128m"
    CPU_LIMIT = "0.5"
    TIMEOUT_SECONDS = 5
    MAX_OUTPUT_SIZE = 10000  # Max characters for stdout/stderr

    def __init__(
        self,
        timeout_seconds: int | None = None,
        memory_limit: str | None = None,
        cpu_limit: str | None = None,
    ):
        """
        Initialize the code runner service.

        Args:
            timeout_seconds: Execution timeout per test (default: 5)
            memory_limit: Docker memory limit (default: "128m")
            cpu_limit: Docker CPU limit (default: "0.5")
        """
        self.timeout_seconds = timeout_seconds or self.TIMEOUT_SECONDS
        self.memory_limit = memory_limit or self.MEMORY_LIMIT
        self.cpu_limit = cpu_limit or self.CPU_LIMIT

    def is_docker_available(self) -> bool:
        """Check if Docker is available and running."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def ensure_image_exists(self) -> bool:
        """Check if the Docker image exists, build if not."""
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", self.DOCKER_IMAGE],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True

            # Image doesn't exist, try to build it
            logger.info("Docker image %s not found, building...", self.DOCKER_IMAGE)
            dockerfile_path = Path(settings.BASE_DIR) / "docker" / "python-runner"

            if not dockerfile_path.exists():
                logger.error("Dockerfile not found at %s", dockerfile_path)
                return False

            result = subprocess.run(
                ["docker", "build", "-t", self.DOCKER_IMAGE, str(dockerfile_path)],
                capture_output=True,
                timeout=120,
            )

            if result.returncode != 0:
                logger.error(
                    "Failed to build Docker image: %s", result.stderr.decode()
                )
                return False

            logger.info("Successfully built Docker image %s", self.DOCKER_IMAGE)
            return True

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error("Error checking/building Docker image: %s", e)
            return False

    def execute_test(
        self,
        code: str,
        function_name: str,
        input_data: dict,
        expected_output: object,
        test_case_id: int,
        test_name: str,
        test_type: str = "return",
    ) -> TestResult:
        """
        Execute code against a single test case.

        Args:
            code: The Python code to execute
            function_name: Name of the function to call
            input_data: Arguments to pass to the function
            expected_output: Expected return value or stdout
            test_case_id: ID of the test case
            test_name: Name of the test case
            test_type: Type of test (return, stdout, assert)

        Returns:
            TestResult with execution details
        """
        try:
            output = self._run_in_docker(code, function_name, input_data)
        except CodeRunnerError as e:
            return TestResult(
                test_case_id=test_case_id,
                test_name=test_name,
                passed=False,
                status="error",
                expected_output=expected_output,
                actual_output=None,
                stdout="",
                stderr="",
                error_message=str(e),
                execution_time_ms=0,
            )

        # Determine pass/fail based on test type
        if not output.success:
            if output.error_type == "timeout":
                status = "timeout"
            else:
                status = "error"
            return TestResult(
                test_case_id=test_case_id,
                test_name=test_name,
                passed=False,
                status=status,
                expected_output=expected_output,
                actual_output=output.return_value,
                stdout=output.stdout[:self.MAX_OUTPUT_SIZE],
                stderr=output.stderr[:self.MAX_OUTPUT_SIZE],
                error_message=output.error,
                execution_time_ms=output.execution_time_ms,
            )

        # Compare output based on test type
        if test_type == "stdout":
            actual = output.stdout.strip()
            expected_str = str(expected_output).strip() if expected_output else ""
            passed = actual == expected_str
            actual_output = actual
        else:  # return value
            passed = self._compare_outputs(output.return_value, expected_output)
            actual_output = output.return_value

        return TestResult(
            test_case_id=test_case_id,
            test_name=test_name,
            passed=passed,
            status="passed" if passed else "failed",
            expected_output=expected_output,
            actual_output=actual_output,
            stdout=output.stdout[:self.MAX_OUTPUT_SIZE],
            stderr=output.stderr[:self.MAX_OUTPUT_SIZE],
            error_message="",
            execution_time_ms=output.execution_time_ms,
        )

    def execute_all_tests(
        self,
        code: str,
        test_cases: list,
    ) -> list[TestResult]:
        """
        Execute code against all test cases.

        Args:
            code: The Python code to execute
            test_cases: List of TestCase model instances

        Returns:
            List of TestResult objects
        """
        results = []

        for test_case in test_cases:
            result = self.execute_test(
                code=code,
                function_name=test_case.function_name,
                input_data=test_case.input_data or {},
                expected_output=test_case.expected_output,
                test_case_id=test_case.id,
                test_name=test_case.name,
                test_type=test_case.test_type,
            )
            results.append(result)

        return results

    def _run_in_docker(
        self,
        code: str,
        function_name: str,
        input_data: dict,
    ) -> ExecutionOutput:
        """
        Run code in an isolated Docker container.

        Args:
            code: Python code to execute
            function_name: Name of function to call
            input_data: Arguments for the function

        Returns:
            ExecutionOutput with results

        Raises:
            DockerNotAvailableError: If Docker is not available
            CodeRunnerError: If execution fails
        """
        if not self.is_docker_available():
            raise DockerNotAvailableError("Docker is not available or not running")

        if not self.ensure_image_exists():
            raise CodeRunnerError(f"Docker image {self.DOCKER_IMAGE} not available")

        # Prepare input JSON
        runner_input = {
            "code": code,
            "function_name": function_name,
            "input_data": input_data,
            "timeout_seconds": self.timeout_seconds,
        }

        try:
            input_json = json.dumps(runner_input)
        except (TypeError, ValueError) as e:
            raise CodeRunnerError(f"Failed to serialize input: {e}")

        # Build Docker command
        docker_cmd = [
            "docker",
            "run",
            "--rm",  # Remove container after execution
            "--network",
            "none",  # No network access
            "--memory",
            self.memory_limit,  # Memory limit
            "--cpus",
            self.cpu_limit,  # CPU limit
            "--read-only",  # Read-only filesystem
            "--tmpfs",
            "/tmp:size=10m",  # Small writable /tmp
            "-i",  # Interactive (for stdin)
            self.DOCKER_IMAGE,
        ]

        try:
            # Run with timeout (add buffer for container startup)
            result = subprocess.run(
                docker_cmd,
                input=input_json,
                capture_output=True,
                timeout=self.timeout_seconds + 10,
                text=True,
            )
        except subprocess.TimeoutExpired:
            return ExecutionOutput(
                success=False,
                return_value=None,
                stdout="",
                stderr="",
                error="Container execution timed out",
                error_type="timeout",
                execution_time_ms=self.timeout_seconds * 1000,
            )
        except Exception as e:
            raise CodeRunnerError(f"Docker execution failed: {e}")

        # Parse output
        try:
            output_data = json.loads(result.stdout)
            return ExecutionOutput(
                success=output_data.get("success", False),
                return_value=output_data.get("return_value"),
                stdout=output_data.get("stdout", ""),
                stderr=output_data.get("stderr", ""),
                error=output_data.get("error", ""),
                error_type=output_data.get("error_type", ""),
                execution_time_ms=output_data.get("execution_time_ms", 0),
            )
        except json.JSONDecodeError:
            # Runner didn't produce valid JSON
            return ExecutionOutput(
                success=False,
                return_value=None,
                stdout=result.stdout[:self.MAX_OUTPUT_SIZE],
                stderr=result.stderr[:self.MAX_OUTPUT_SIZE],
                error="Runner produced invalid output",
                error_type="runner_error",
                execution_time_ms=0,
            )

    def _compare_outputs(self, actual: object, expected: object) -> bool:
        """
        Compare actual and expected outputs with tolerance for floating point.

        Args:
            actual: The actual output from code execution
            expected: The expected output

        Returns:
            True if outputs match, False otherwise
        """
        # Handle None cases
        if actual is None and expected is None:
            return True
        if actual is None or expected is None:
            return False

        # Handle float comparison with tolerance
        if isinstance(actual, float) and isinstance(expected, (int, float)):
            return abs(actual - expected) < 1e-9
        if isinstance(expected, float) and isinstance(actual, (int, float)):
            return abs(actual - expected) < 1e-9

        # Handle list/tuple comparison
        if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
            if len(actual) != len(expected):
                return False
            return all(
                self._compare_outputs(a, e) for a, e in zip(actual, expected)
            )

        # Handle dict comparison
        if isinstance(actual, dict) and isinstance(expected, dict):
            if set(actual.keys()) != set(expected.keys()):
                return False
            return all(
                self._compare_outputs(actual[k], expected[k]) for k in actual
            )

        # Direct comparison
        return actual == expected


# Singleton instance
_code_runner: CodeRunnerService | None = None


def get_code_runner() -> CodeRunnerService:
    """Get the singleton CodeRunnerService instance."""
    global _code_runner
    if _code_runner is None:
        _code_runner = CodeRunnerService()
    return _code_runner
