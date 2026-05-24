"""Resilient websocket health and recovery decisions."""

from __future__ import annotations

from .models import WebsocketHealthDecision, WebsocketStreamState


class WebsocketManager:
    """Evaluate stream health for native exchange websocket feeds."""

    def __init__(
        self,
        *,
        stale_message_ms: int = 3_000,
        stale_heartbeat_ms: int = 5_000,
        high_latency_ms: int = 1_000,
        max_reconnect_attempts: int = 5,
    ) -> None:
        self.stale_message_ms = stale_message_ms
        self.stale_heartbeat_ms = stale_heartbeat_ms
        self.high_latency_ms = high_latency_ms
        self.max_reconnect_attempts = max_reconnect_attempts

    def evaluate(self, state: WebsocketStreamState) -> WebsocketHealthDecision:
        """Return reconnect and staleness action for a stream."""

        if not state.connected:
            return WebsocketHealthDecision(
                healthy=False,
                reconnect=True,
                stale=True,
                reason=f"{state.stream_name} is disconnected.",
                target_action="reconnect",
            )

        if state.sequence_gap_detected:
            return WebsocketHealthDecision(
                healthy=False,
                reconnect=True,
                stale=True,
                reason=f"{state.stream_name} sequence gap detected.",
                target_action="resubscribe_and_snapshot_recover",
            )

        if (
            state.last_message_age_ms >= self.stale_message_ms
            or state.heartbeat_age_ms >= self.stale_heartbeat_ms
        ):
            action = (
                "lockdown_stream"
                if state.reconnect_attempts >= self.max_reconnect_attempts
                else "reconnect"
            )
            return WebsocketHealthDecision(
                healthy=False,
                reconnect=True,
                stale=True,
                reason=f"{state.stream_name} is stale.",
                target_action=action,
            )

        if state.latency_ms >= self.high_latency_ms:
            return WebsocketHealthDecision(
                healthy=False,
                reconnect=False,
                stale=False,
                reason=f"{state.stream_name} latency is elevated.",
                target_action="deprioritize_latency_sensitive_execution",
            )

        return WebsocketHealthDecision(
            healthy=True,
            reconnect=False,
            stale=False,
            reason=f"{state.stream_name} is healthy.",
            target_action="none",
        )

