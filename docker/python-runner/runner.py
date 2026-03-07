#!/usr/bin/env python3
"""
Secure Python code execution runner for coding challenges.

This script runs user-submitted Python code in a restricted environment,
capturing the output and any errors for evaluation.

Security measures:
- Restricted builtins (no file I/O, network, subprocess, etc.)
- Execution timeout via signal
- Memory limits enforced by Docker
- No access to sensitive modules
"""

import json
import signal
import sys
import traceback
from io import StringIO
from typing import Any


# Modules that are explicitly blocked from import
BLOCKED_MODULES = frozenset({
    "os",
    "subprocess",
    "socket",
    "shutil",
    "pathlib",
    "multiprocessing",
    "threading",
    "ctypes",
    "pickle",
    "shelve",
    "marshal",
    "importlib",
    "builtins",
    "__builtins__",
    "sys",
    "code",
    "codeop",
    "compile",
    "exec",
    "eval",
    "requests",
    "urllib",
    "http",
    "ftplib",
    "smtplib",
    "telnetlib",
    "ssl",
    "asyncio",
    "concurrent",
    "gc",
    "resource",
    "signal",
    "pty",
    "tty",
    "termios",
    "fcntl",
    "mmap",
    "sysconfig",
    "platform",
    "getpass",
    "pwd",
    "grp",
    "spwd",
    "crypt",
})

# Safe builtins that user code can access
SAFE_BUILTINS = {
    # Types
    "bool": bool,
    "int": int,
    "float": float,
    "str": str,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "frozenset": frozenset,
    "bytes": bytes,
    "bytearray": bytearray,
    "type": type,
    "object": object,
    # Functions
    "abs": abs,
    "all": all,
    "any": any,
    "bin": bin,
    "callable": callable,
    "chr": chr,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "format": format,
    "hash": hash,
    "hex": hex,
    "id": id,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "oct": oct,
    "ord": ord,
    "pow": pow,
    "print": print,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "slice": slice,
    "sorted": sorted,
    "sum": sum,
    "zip": zip,
    # Exceptions
    "Exception": Exception,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "AttributeError": AttributeError,
    "RuntimeError": RuntimeError,
    "StopIteration": StopIteration,
    "ZeroDivisionError": ZeroDivisionError,
    # Constants
    "True": True,
    "False": False,
    "None": None,
}

# Safe modules that can be imported
SAFE_MODULES = frozenset({
    "math",
    "random",
    "string",
    "re",
    "json",
    "collections",
    "itertools",
    "functools",
    "operator",
    "copy",
    "heapq",
    "bisect",
    "datetime",
    "decimal",
    "fractions",
    "statistics",
    "typing",
    "dataclasses",
    "abc",
    "numbers",
    "enum",
})


class TimeoutError(Exception):
    """Raised when code execution times out."""
    pass


class SecurityError(Exception):
    """Raised when code attempts a forbidden operation."""
    pass


def timeout_handler(signum: int, frame: Any) -> None:
    """Signal handler for execution timeout."""
    raise TimeoutError("Execution timed out")


def create_restricted_import(allowed_modules: frozenset[str]):
    """Create a restricted __import__ function."""
    original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def restricted_import(
        name: str,
        globals: dict | None = None,
        locals: dict | None = None,
        fromlist: tuple = (),
        level: int = 0,
    ):
        # Check top-level module name
        top_level = name.split(".")[0]

        if top_level in BLOCKED_MODULES:
            raise SecurityError(f"Import of '{name}' is not allowed")

        if top_level not in allowed_modules:
            raise SecurityError(f"Import of '{name}' is not allowed")

        return original_import(name, globals, locals, fromlist, level)

    return restricted_import


def execute_code(
    code: str,
    function_name: str,
    input_data: dict[str, Any],
    timeout_seconds: int = 5,
) -> dict[str, Any]:
    """
    Execute user code and call the specified function with input data.

    Args:
        code: The Python code to execute
        function_name: Name of the function to call
        input_data: Keyword arguments to pass to the function
        timeout_seconds: Maximum execution time

    Returns:
        Dict with: success, return_value, stdout, stderr, error, execution_time_ms
    """
    import time

    result = {
        "success": False,
        "return_value": None,
        "stdout": "",
        "stderr": "",
        "error": "",
        "error_type": "",
        "execution_time_ms": 0,
    }

    # Set up timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_seconds)

    # Capture stdout/stderr
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = StringIO()
    sys.stderr = StringIO()

    start_time = time.perf_counter()

    try:
        # Create restricted execution environment
        restricted_builtins = SAFE_BUILTINS.copy()
        restricted_builtins["__import__"] = create_restricted_import(SAFE_MODULES)

        # Create namespace for execution
        namespace = {"__builtins__": restricted_builtins}

        # Execute the user's code to define functions/classes
        exec(code, namespace)

        # Check if the function exists
        if function_name not in namespace:
            raise NameError(f"Function '{function_name}' is not defined")

        func = namespace[function_name]
        if not callable(func):
            raise TypeError(f"'{function_name}' is not callable")

        # Call the function with input data
        return_value = func(**input_data)

        # Success
        result["success"] = True
        result["return_value"] = return_value

    except TimeoutError as e:
        result["error"] = str(e)
        result["error_type"] = "timeout"

    except SecurityError as e:
        result["error"] = str(e)
        result["error_type"] = "security"

    except SyntaxError as e:
        result["error"] = f"Syntax error: {e}"
        result["error_type"] = "syntax"

    except NameError as e:
        result["error"] = str(e)
        result["error_type"] = "name"

    except TypeError as e:
        result["error"] = str(e)
        result["error_type"] = "type"

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        result["error_type"] = "runtime"

    finally:
        # Cancel timeout
        signal.alarm(0)

        # Calculate execution time
        end_time = time.perf_counter()
        result["execution_time_ms"] = int((end_time - start_time) * 1000)

        # Capture output
        result["stdout"] = sys.stdout.getvalue()
        result["stderr"] = sys.stderr.getvalue()

        # Restore stdout/stderr
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    return result


def main():
    """Main entry point for the runner."""
    # Read input from stdin (JSON format)
    try:
        input_json = sys.stdin.read()
        input_data = json.loads(input_json)
    except json.JSONDecodeError as e:
        print(json.dumps({
            "success": False,
            "error": f"Invalid JSON input: {e}",
            "error_type": "input",
        }))
        sys.exit(1)

    # Extract parameters
    code = input_data.get("code", "")
    function_name = input_data.get("function_name", "solution")
    test_input = input_data.get("input_data", {})
    timeout = input_data.get("timeout_seconds", 5)

    # Execute and output result
    result = execute_code(code, function_name, test_input, timeout)

    # Serialize result, handling non-JSON-serializable return values
    try:
        output = json.dumps(result)
    except (TypeError, ValueError):
        # If return value isn't JSON-serializable, convert to string
        result["return_value"] = repr(result["return_value"])
        output = json.dumps(result)

    print(output)


if __name__ == "__main__":
    main()
