"""The tool registry: what the agent may do, and what it must prove before doing it.

**Arguments arriving here are model output, which is to say they are untrusted input.**

That framing is the whole design. A tool call is not a function call that happens to come
from a model -- it is a request from outside the system, with the same standing as a query
string. The model is good at producing plausible arguments, and plausible is not the same
as real: a ticket id of ``"the one about printers"``, a status of ``"urgent"`` where the
enum holds priorities, an extra ``limit`` parameter the tool never declared.

So validation lives here, at the boundary, and runs on every call. A tool body may assume
its arguments are well-typed because nothing else can reach it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from agentdesk.llm.types import ToolCall

#: JSON types a parameter may declare. Narrow on purpose -- every addition is another
#: shape the validator has to be right about.
ParamType = Literal["string", "integer", "boolean"]


class ToolError(RuntimeError):
    """Raised when a tool fails in a way the agent should be told about.

    Distinct from a crash: this becomes an observation the model can read and react to,
    which is how "that ticket does not exist" turns into a sensible reply rather than a
    500.
    """


class UnknownTool(KeyError):
    """Raised when the model asks for a tool that is not registered."""


class InvalidArguments(ValueError):
    """Raised when a call's arguments do not satisfy the tool's declared parameters."""


@dataclass(frozen=True)
class Param:
    """One declared parameter.

    Attributes:
        name: Parameter name.
        type: Declared JSON type.
        description: What it means. Shown to the model; **not** part of the tool digest,
            so this can be improved without invalidating the recorded conversations.
        required: Whether a call must supply it.
        enum: Permitted values, if the parameter is closed.
    """

    name: str
    type: ParamType
    description: str
    required: bool = True
    enum: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ToolSpec:
    """One tool: its contract and its implementation.

    Attributes:
        name: Stable identifier the model uses.
        description: One or two sentences for the prompt.
        parameters: Declared parameters.
        handler: The implementation. Receives validated keyword arguments and returns a
            string, because what it returns becomes an observation the model reads.
    """

    name: str
    description: str
    parameters: tuple[Param, ...]
    handler: Callable[..., str] = field(repr=False, default=lambda: "")

    def schema(self) -> dict:
        """Return the JSON-Schema-shaped description shown to the model.

        This is the **single source** for what the prompt advertises. The prompt layer
        renders this rather than restating it, so the two cannot drift -- a tool gaining
        a parameter updates the prompt automatically, and
        ``tests/test_prompt.py::test_the_prompt_advertises_exactly_the_registered_contract``
        fails loudly if anyone reintroduces a hand-written copy.
        """
        properties: dict[str, dict] = {}
        for param in self.parameters:
            entry: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum is not None:
                entry["enum"] = list(param.enum)
            properties[param.name] = entry
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": [p.name for p in self.parameters if p.required],
            },
        }

    def validate(self, arguments: dict) -> dict:
        """Check and coerce one call's arguments.

        Args:
            arguments: Arguments exactly as the model produced them.

        Returns:
            Validated arguments, ready to pass as keywords.

        Raises:
            InvalidArguments: If anything is missing, unknown, wrongly typed or outside a
                declared enum. The message names the offending parameter, because it
                becomes an observation the model is expected to act on.
        """
        declared = {param.name: param for param in self.parameters}

        unknown = set(arguments) - set(declared)
        if unknown:
            raise InvalidArguments(
                f"{self.name} does not take {sorted(unknown)}; "
                f"it takes {sorted(declared)}"
            )

        missing = [
            param.name
            for param in self.parameters
            if param.required and param.name not in arguments
        ]
        if missing:
            raise InvalidArguments(f"{self.name} requires {missing}")

        validated: dict[str, Any] = {}
        for name, value in arguments.items():
            validated[name] = _coerce(self.name, declared[name], value)
        return validated


def _coerce(tool: str, param: Param, value: Any) -> Any:
    """Return ``value`` as ``param``'s declared type, or raise.

    Accepts the string form of an integer, because a model that has been told a parameter
    is an integer still sometimes sends ``"42"``, and rejecting that teaches nothing. It
    does **not** accept ``"forty-two"``, ``12.5`` or ``True`` -- those are not an integer
    written down, they are a different value.
    """
    if param.type == "integer":
        if isinstance(value, bool):
            raise InvalidArguments(f"{tool}.{param.name} must be an integer, got a boolean")
        if isinstance(value, int):
            coerced = value
        elif isinstance(value, str) and value.strip().lstrip("-").isdigit():
            coerced = int(value.strip())
        else:
            raise InvalidArguments(
                f"{tool}.{param.name} must be an integer, got {value!r}"
            )
        return coerced

    if param.type == "boolean":
        if not isinstance(value, bool):
            raise InvalidArguments(f"{tool}.{param.name} must be a boolean, got {value!r}")
        return value

    if not isinstance(value, str):
        raise InvalidArguments(f"{tool}.{param.name} must be a string, got {value!r}")
    if param.enum is not None and value not in param.enum:
        raise InvalidArguments(
            f"{tool}.{param.name} must be one of {list(param.enum)}, got {value!r}"
        )
    return value


class Registry:
    """The tools available to the agent."""

    def __init__(self, tools: tuple[ToolSpec, ...] = ()) -> None:
        self._tools: dict[str, ToolSpec] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: ToolSpec) -> None:
        """Add a tool.

        Raises:
            ValueError: If the name is already taken. Silently replacing would make the
                set of available tools depend on import order.
        """
        if tool.name in self._tools:
            raise ValueError(f"{tool.name} is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSpec:
        """Return one tool.

        Raises:
            UnknownTool: If no tool has this name.
        """
        try:
            return self._tools[name]
        except KeyError:
            raise UnknownTool(
                f"{name!r} is not a tool; available: {sorted(self._tools)}"
            ) from None

    def specs(self) -> tuple[ToolSpec, ...]:
        """Return every tool, sorted by name so the order is stable across processes."""
        return tuple(sorted(self._tools.values(), key=lambda tool: tool.name))

    def invoke(self, call: ToolCall) -> str:
        """Validate and run one tool call.

        Args:
            call: The model's request.

        Returns:
            The tool's output, which becomes an observation.

        Raises:
            UnknownTool: If the tool does not exist.
            InvalidArguments: If the arguments do not satisfy the contract.
            ToolError: If the tool ran and failed.
        """
        tool = self.get(call.name)
        arguments = tool.validate(call.arguments)
        return tool.handler(**arguments)

    def catalog(self) -> str:
        """Return every tool's schema as JSON, for the prompt and for debugging."""
        return json.dumps([tool.schema() for tool in self.specs()], indent=2)
