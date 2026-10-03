"""The tool registry and its validation.

**The frame for every test here: arguments produced by a model are untrusted input.**

Not "input from a component we wrote", not "input we can expect to be well-formed" --
untrusted, in the same sense a query string is. The model is fluent, and fluency produces
arguments that read correctly and are not. A test suite that only exercises well-formed
calls is testing the easy half.
"""

from __future__ import annotations

import pytest

from agentdesk.assistant.registry import (
    InvalidArguments,
    Param,
    Registry,
    ToolError,
    ToolSpec,
    UnknownTool,
)
from agentdesk.llm.types import ToolCall


def call(name: str, **arguments: object) -> ToolCall:
    return ToolCall(id="c0", name=name, arguments=dict(arguments))


def test_a_valid_call_runs(registry) -> None:
    assert registry.invoke(call("echo", text="hello")) == "echo: hello"


def test_an_unregistered_tool_is_refused(registry) -> None:
    with pytest.raises(UnknownTool, match="not a tool"):
        registry.invoke(call("delete_everything", confirm="yes"))


def test_a_hallucinated_identifier_never_reaches_the_handler(registry) -> None:
    """**The property ex-053 turns on, stated directly.**

    ``count`` takes an integer. A model that has read a ticket about "the printer one"
    will, sooner or later, pass that phrase where a number belongs. Unvalidated, it
    reaches the handler and from there the database, where it becomes either a driver
    error nobody can trace back or -- worse -- a query that runs.
    """
    seen: list[object] = []
    registry.register(
        ToolSpec(
            name="records_what_it_got",
            description="Test double.",
            parameters=(Param(name="n", type="integer", description="A number."),),
            handler=lambda n: seen.append(n) or "ok",
        )
    )

    with pytest.raises(InvalidArguments, match="must be an integer"):
        registry.invoke(call("records_what_it_got", n="the printer one"))

    assert seen == [], "the handler ran with an argument that was never checked"


def test_a_missing_required_argument_is_refused(registry) -> None:
    with pytest.raises(InvalidArguments, match="requires"):
        registry.invoke(call("echo"))


def test_an_undeclared_argument_is_refused(registry) -> None:
    """Silently dropping it would let a model believe a limit was applied when it was not."""
    with pytest.raises(InvalidArguments, match="does not take"):
        registry.invoke(call("echo", text="hi", limit=5))


def test_a_value_outside_an_enum_is_refused(registry) -> None:
    with pytest.raises(InvalidArguments, match="must be one of"):
        registry.invoke(call("fact", topic="mileage"))


def test_the_string_form_of_an_integer_is_accepted(registry) -> None:
    """A model told a parameter is an integer still sometimes sends ``"42"``.

    Refusing that teaches nothing and costs a round trip. Accepting ``"forty-two"`` would
    be a different matter, and the next test covers it.
    """
    assert registry.invoke(call("count", n="7")) == "counted to 7"
    assert registry.invoke(call("count", n=-3)) == "counted to -3"


@pytest.mark.parametrize("value", ["forty-two", 12.5, True, None, [1], {"n": 1}])
def test_things_that_are_not_an_integer_are_refused(registry, value: object) -> None:
    """``True`` is in this list on purpose: ``isinstance(True, int)`` is true in Python,
    so a naive type check accepts a boolean as a ticket id."""
    with pytest.raises(InvalidArguments):
        registry.invoke(call("count", n=value))


def test_a_tool_that_fails_raises_a_tool_error(registry) -> None:
    """Distinct from a validation failure: the call was well-formed, the work failed."""
    registry.register(
        ToolSpec(
            name="always_fails",
            description="Test double.",
            parameters=(),
            handler=lambda: (_ for _ in ()).throw(ToolError("nothing there")),
        )
    )
    with pytest.raises(ToolError, match="nothing there"):
        registry.invoke(call("always_fails"))


def test_registering_a_duplicate_name_is_refused() -> None:
    """Otherwise the available tools would depend on import order."""
    spec = ToolSpec(
        name="dup",
        description="x",
        parameters=(),
        handler=lambda: "ok",
    )
    registry = Registry((spec,))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(spec)


def test_specs_are_returned_in_a_stable_order(registry) -> None:
    """The order reaches the prompt and the tool digest, so it must not vary by process."""
    assert [spec.name for spec in registry.specs()] == sorted(
        spec.name for spec in registry.specs()
    )


def test_the_schema_matches_what_validation_enforces(registry) -> None:
    """The contract shown to the model and the contract applied to it are one object.

    Checked here rather than assumed, because these are the two halves whose drift
    ex-054 is about -- this is the same claim from the registry's side.
    """
    for spec in registry.specs():
        schema = spec.schema()
        declared = {param.name for param in spec.parameters}
        assert set(schema["parameters"]["properties"]) == declared
        assert set(schema["parameters"]["required"]) == {
            param.name for param in spec.parameters if param.required
        }
