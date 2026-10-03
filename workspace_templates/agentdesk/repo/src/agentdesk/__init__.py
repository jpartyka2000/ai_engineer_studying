"""agentdesk -- a support ticket desk with an assistant bolted on three years later.

The layering matters, because most of what can go wrong here is a layering mistake:

``tickets``
    The original product. CRUD, search, assignment and SLA timers. **Knows nothing about
    the assistant** and must keep working at its old speed whether the assistant is fast,
    slow or on fire.

``assistant``
    The agent. A tool registry, the prompt assembled from it, and the loop that runs until
    the model stops asking for tools. Depends on ``tickets``; never the reverse.

``serving``
    The control plane for the self-hosted model: VRAM accounting, the paged KV allocator
    and the admission policy. Pure arithmetic, no accelerator, no inference.

``obs``
    Probes that let a test assert *why* something is slow rather than *that* it is.

The two rules the reviews keep coming back to: the assistant may not make the desk slower,
and the desk may not import the assistant.
"""

__version__ = "2.3.0"

__all__ = ["__version__"]
