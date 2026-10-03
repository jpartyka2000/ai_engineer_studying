"""VRAM arithmetic.

Every number here is checked against a value computed by hand in the test itself rather
than against whatever the implementation returns. A test that asserts
``kv_bytes_per_token(spec) == kv_bytes_per_token(spec)`` passes forever and means nothing;
these spell the formula out a second way so that a change to the first one is visible.
"""

from __future__ import annotations

import pytest

from agentdesk.serving import DESK_8B
from agentdesk.serving.memory import (
    CapacityError,
    ModelSpec,
    activation_bytes,
    dtype_bytes,
    kv_bytes_for_request,
    kv_bytes_per_token,
    max_concurrent_requests,
    plan_budget,
    weight_bytes,
)

GIB = 1024**3


def test_bf16_and_fp16_are_the_same_size() -> None:
    """bf16 trades mantissa for range, not bytes. Assuming otherwise is a 2x error."""
    assert dtype_bytes("bf16") == dtype_bytes("fp16") == 2
    assert dtype_bytes("fp32") == 4
    assert dtype_bytes("fp8") == 1


def test_an_unknown_dtype_raises_rather_than_defaulting() -> None:
    """A default here would silently halve or double the entire budget."""
    with pytest.raises(KeyError):
        dtype_bytes("int4")


def test_weights_are_params_times_dtype() -> None:
    spec = ModelSpec(name="t", params=1_000_000_000, layers=4, kv_heads=2, head_dim=64)
    assert weight_bytes(spec) == 2_000_000_000


def test_kv_per_token_counts_both_k_and_v() -> None:
    """**The factor of 2 is the most commonly dropped term in this formula.**

    Spelled out: two tensors, per layer, per KV head, head_dim wide, at the cache dtype.
    """
    spec = ModelSpec(
        name="t", params=1, layers=32, kv_heads=8, head_dim=128, kv_dtype="fp16"
    )
    expected = 2 * 32 * 8 * 128 * 2
    assert kv_bytes_per_token(spec) == expected == 131_072


def test_grouped_query_attention_shows_up_entirely_in_the_cache() -> None:
    """8 KV heads against 32 is a 4x saving, and it lands here and nowhere else."""
    gqa = ModelSpec(name="gqa", params=1, layers=32, kv_heads=8, head_dim=128)
    mha = ModelSpec(name="mha", params=1, layers=32, kv_heads=32, head_dim=128)
    assert kv_bytes_per_token(mha) == 4 * kv_bytes_per_token(gqa)


def test_a_request_is_sized_on_its_peak_not_its_prompt() -> None:
    """**The property ex-059 turns on, stated directly.**

    The cache holds the prompt *and* everything generated so far, so the peak is at the
    last token. Sizing on the prompt alone is how a request is admitted happily and then
    fails two hundred tokens into its answer.
    """
    per_token = kv_bytes_per_token(DESK_8B)
    assert kv_bytes_for_request(DESK_8B, prompt_tokens=900, max_new_tokens=200) == (
        per_token * 1100
    )


def test_a_request_longer_than_the_context_window_is_rejected() -> None:
    with pytest.raises(ValueError, match="context"):
        kv_bytes_for_request(DESK_8B, prompt_tokens=8000, max_new_tokens=500)


def test_activation_headroom_is_never_zero() -> None:
    """Treating it as zero is what lets a planner fill the card and fall over."""
    assert activation_bytes(DESK_8B, batch_size=1) > 0
    assert activation_bytes(DESK_8B, batch_size=32) == 32 * activation_bytes(
        DESK_8B, batch_size=1
    )


def test_the_budget_adds_up() -> None:
    budget = plan_budget(DESK_8B, vram_bytes=24 * GIB)
    assert budget.weights + budget.reserved + budget.kv_available == budget.total
    assert 0 < budget.utilization < 1


def test_a_model_too_large_for_the_card_fails_loudly() -> None:
    """Not a judgment call: no batch size makes this work, so say so now."""
    huge = ModelSpec(name="huge", params=70_000_000_000, layers=80, kv_heads=8, head_dim=128)
    with pytest.raises(CapacityError, match="does not fit"):
        plan_budget(huge, vram_bytes=24 * GIB)


def test_concurrency_is_the_kv_budget_divided_by_the_peak() -> None:
    budget = plan_budget(DESK_8B, vram_bytes=24 * GIB)
    per_request = kv_bytes_for_request(DESK_8B, prompt_tokens=900, max_new_tokens=200)
    assert max_concurrent_requests(
        DESK_8B, budget=budget, prompt_tokens=900, max_new_tokens=200
    ) == budget.kv_available // per_request


def test_the_served_model_fits_its_card_with_room_to_work() -> None:
    """A guard on the configuration itself, not on the arithmetic.

    If somebody changes the dtype or the head count and the model stops leaving usable
    cache, that is a deployment that would have OOMed on its first request.
    """
    budget = plan_budget(DESK_8B, vram_bytes=24 * GIB)
    assert budget.kv_available > 4 * GIB
