# Author: Bradley R. Kinnard
"""Event bus for the UI live stream (Phase 3.3).

The BeliefService publishes a small JSON event on every successful
append; the ``/ui/events/stream`` WebSocket subscribes to the same
channel and forwards events to connected operators.

Why we do not couple to the SQLAlchemy commit lifecycle:

* The chain — the BeliefRecord rows themselves — is the source of
  truth. A client that misses an event refetches via
  ``/runs/{id}/trace``.
* Events are advisory, fire-and-forget. Coupling to commit
  semantics would force the publisher into every transaction
  participant, complicating tests and adding a failure mode that
  cannot improve correctness of the chain.

What we do guard against:

* Redis being unreachable. The publisher silently degrades to a
  no-op so a broken broker can't break belief writes. A WARNING
  is logged on the first failure per process; subsequent failures
  are throttled to avoid log spam.
* The publisher being a module-level singleton. Tests must be
  able to inject a fake; ``set_belief_event_bus`` is the override
  hook.
"""

from ironroot.events.bus import (
    BeliefEventBus,
    InMemoryBeliefEventBus,
    NullBeliefEventBus,
    RedisBeliefEventBus,
    get_belief_event_bus,
    reset_belief_event_bus,
    set_belief_event_bus,
)

__all__ = [
    "BeliefEventBus",
    "InMemoryBeliefEventBus",
    "NullBeliefEventBus",
    "RedisBeliefEventBus",
    "get_belief_event_bus",
    "reset_belief_event_bus",
    "set_belief_event_bus",
]
