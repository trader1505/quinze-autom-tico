"""Independent watchdog decisions for critical service health."""

from __future__ import annotations

from .models import SafeMode, WatchdogDecision, WatchdogHeartbeat


class WatchdogService:
    """Monitor critical service heartbeats independently from trading logic."""

    def __init__(
        self,
        *,
        stale_heartbeat_ms: int = 7_500,
        critical_heartbeat_ms: int = 15_000,
        max_queue_backlog: int = 5_000,
        max_error_count: int = 25,
    ) -> None:
        self.stale_heartbeat_ms = stale_heartbeat_ms
        self.critical_heartbeat_ms = critical_heartbeat_ms
        self.max_queue_backlog = max_queue_backlog
        self.max_error_count = max_error_count

    def evaluate(self, heartbeats: tuple[WatchdogHeartbeat, ...]) -> WatchdogDecision:
        actions: list[str] = []
        reasons: list[str] = []
        target_mode = SafeMode.NORMAL

        for heartbeat in heartbeats:
            if heartbeat.last_seen_ms >= self.critical_heartbeat_ms:
                target_mode = SafeMode.LOCKDOWN
                actions.append(f"restart:{heartbeat.service_name}")
                reasons.append(
                    f"{heartbeat.service_name} heartbeat is critically stale."
                )
                continue

            if heartbeat.last_seen_ms >= self.stale_heartbeat_ms:
                target_mode = self._max_mode(target_mode, SafeMode.SURVIVAL)
                actions.append(f"safe_mode:{heartbeat.service_name}")
                reasons.append(f"{heartbeat.service_name} heartbeat is stale.")

            if heartbeat.queue_backlog >= self.max_queue_backlog:
                target_mode = self._max_mode(target_mode, SafeMode.DEFENSIVE)
                actions.append(f"throttle:{heartbeat.service_name}")
                reasons.append(f"{heartbeat.service_name} queue backlog is elevated.")

            if heartbeat.error_count >= self.max_error_count:
                target_mode = self._max_mode(target_mode, SafeMode.SURVIVAL)
                actions.append(f"restart:{heartbeat.service_name}")
                reasons.append(f"{heartbeat.service_name} error count is elevated.")

        return WatchdogDecision(
            healthy=not reasons,
            target_mode=target_mode,
            actions=tuple(dict.fromkeys(actions)),
            reasons=tuple(reasons),
        )

    def _max_mode(self, left: SafeMode, right: SafeMode) -> SafeMode:
        order = {
            SafeMode.NORMAL: 0,
            SafeMode.CAUTION: 1,
            SafeMode.DEFENSIVE: 2,
            SafeMode.SURVIVAL: 3,
            SafeMode.LOCKDOWN: 4,
        }
        return left if order[left] >= order[right] else right

