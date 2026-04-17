"""Finite-state machine for deterministic bot orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Set

from .models import EngineState


@dataclass(frozen=True)
class StateTransition:
    """Represents a valid state transition."""

    origin: EngineState
    target: EngineState


class InvalidTransitionError(RuntimeError):
    """Raised when an invalid transition is requested."""


class BotStateMachine:
    """Deterministic state machine with explicit transitions."""

    _allowed: Dict[EngineState, Set[EngineState]] = {
        EngineState.IDLE: {EngineState.ANALYZING, EngineState.PAUSED},
        EngineState.ANALYZING: {
            EngineState.IDLE,
            EngineState.OPENING,
            EngineState.MANAGING,
            EngineState.PAUSED,
        },
        EngineState.OPENING: {EngineState.MANAGING, EngineState.IDLE, EngineState.PAUSED},
        EngineState.MANAGING: {
            EngineState.HEDGING,
            EngineState.RECOVERY,
            EngineState.ANALYZING,
            EngineState.IDLE,
            EngineState.PAUSED,
        },
        EngineState.HEDGING: {EngineState.MANAGING, EngineState.RECOVERY, EngineState.PAUSED},
        EngineState.RECOVERY: {EngineState.MANAGING, EngineState.HEDGING, EngineState.PAUSED},
        EngineState.PAUSED: {EngineState.IDLE},
    }

    def __init__(self) -> None:
        self._state = EngineState.IDLE

    @property
    def current_state(self) -> EngineState:
        """Returns current state."""
        return self._state

    def transition_to(self, target: EngineState) -> StateTransition:
        """Performs a safe transition to target state."""
        if target not in self._allowed[self._state]:
            raise InvalidTransitionError(
                f"Invalid transition: {self._state.value} -> {target.value}"
            )
        previous = self._state
        self._state = target
        return StateTransition(origin=previous, target=target)
