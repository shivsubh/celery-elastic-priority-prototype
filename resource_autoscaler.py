"""
Prototype: Resource Autoscaler
================================
Dynamically adjusts Celery worker concurrency based on system resources.
"""

import time
import logging
from dataclasses import dataclass
from enum import Enum

from resource_monitor import ResourceMonitor
from priority_scheduler import PriorityScheduler

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class ScaleDirection(Enum):
    UP = "up"
    DOWN = "down"
    HOLD = "hold"


@dataclass
class ScaleDecision:
    direction: ScaleDirection
    current: int
    target: int
    reason: str
    cpu_percent: float
    memory_percent: float
    pending_tasks: int


class ResourceAutoscaler:
    def __init__(
        self,
        resource_monitor,
        priority_scheduler=None,
        min_concurrency: int = 4,
        max_concurrency: int = 200,
        scale_up_threshold: float = 0.6,
        scale_down_threshold: float = 0.2,
        scale_up_step: int = 10,
        scale_down_step: int = 5,
        cooldown_seconds: float = 30.0,
        check_interval: float = 10.0,
    ):
        self.monitor = resource_monitor
        self.scheduler = priority_scheduler
        self.min_concurrency = min_concurrency
        self.max_concurrency = max_concurrency
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
        self.scale_up_step = scale_up_step
        self.scale_down_step = scale_down_step
        self.cooldown_seconds = cooldown_seconds
        self.check_interval = check_interval
        self._current_concurrency = min_concurrency
        self._last_scale_time = 0.0
        self._decisions: list[ScaleDecision] = []

    @property
    def current_concurrency(self) -> int:
        return self._current_concurrency

    def make_decision(self, pending_tasks: int) -> ScaleDecision:
        snap = self.monitor.current_snapshot
        available_capacity = self.monitor.get_available_capacity()
        current = self._current_concurrency
        elapsed = time.time() - self._last_scale_time

        if elapsed < self.cooldown_seconds:
            return ScaleDecision(
                direction=ScaleDirection.HOLD,
                current=current,
                target=current,
                reason=f"cooldown ({self.cooldown_seconds - elapsed:.0f}s remaining)",
                cpu_percent=snap.cpu_percent,
                memory_percent=snap.memory_percent,
                pending_tasks=pending_tasks,
            )

        utilization = 1.0 - (available_capacity / max(current, 1))

        if pending_tasks > 0 and self.monitor.is_healthy():
            workers_needed = min(
                pending_tasks,
                self.scale_up_step,
                available_capacity,
                self.max_concurrency - current,
            )
            if workers_needed > 0:
                return ScaleDecision(
                    direction=ScaleDirection.UP,
                    current=current,
                    target=current + workers_needed,
                    reason=f"{pending_tasks} pending, {available_capacity} capacity available",
                    cpu_percent=snap.cpu_percent,
                    memory_percent=snap.memory_percent,
                    pending_tasks=pending_tasks,
                )

        if pending_tasks == 0 and utilization < self.scale_down_threshold:
            target = max(self.min_concurrency, current - self.scale_down_step)
            if target < current:
                return ScaleDecision(
                    direction=ScaleDirection.DOWN,
                    current=current,
                    target=target,
                    reason=f"utilization {utilization:.1%} < {self.scale_down_threshold:.1%}",
                    cpu_percent=snap.cpu_percent,
                    memory_percent=snap.memory_percent,
                    pending_tasks=pending_tasks,
                )

        return ScaleDecision(
            direction=ScaleDirection.HOLD,
            current=current,
            target=current,
            reason="no scaling action needed",
            cpu_percent=snap.cpu_percent,
            memory_percent=snap.memory_percent,
            pending_tasks=pending_tasks,
        )

    def apply_decision(self, decision: ScaleDecision):
        if decision.direction == ScaleDirection.HOLD:
            return

        old = self._current_concurrency
        self._current_concurrency = decision.target
        self._last_scale_time = time.time()
        self._decisions.append(decision)

        if self.scheduler:
            self.scheduler.adjust_total_concurrency(decision.target)

        logger.info(
            "Scaled %s: %d -> %d (%s)",
            decision.direction.value,
            old,
            decision.target,
            decision.reason,
        )

    def tick(self, pending_tasks: int):
        decision = self.make_decision(pending_tasks)
        self.apply_decision(decision)
        return decision


if __name__ == "__main__":

    print("Resource Autoscaler Prototype\\n" + "=" * 50)

    monitor = ResourceMonitor(max_cpu_percent=80, max_memory_percent=85)
    monitor.start()
    time.sleep(1)

    scheduler = PriorityScheduler(total_concurrency=20)
    autoscaler = ResourceAutoscaler(
        resource_monitor=monitor,
        priority_scheduler=scheduler,
        min_concurrency=4,
        max_concurrency=100,
        cooldown_seconds=5,
    )

    workload = [
        (0, "Idle system"),
        (50, "Burst of monitoring tasks"),
        (100, "Heavy load - many pending checks"),
        (20, "Load decreasing"),
        (0, "Back to idle"),
    ]

    for pending, description in workload:
        print(f"\\n--- {description} (pending={pending}) ---")
        decision = autoscaler.tick(pending_tasks=pending)
        print(
            f"  Decision: {decision.direction.value} ({decision.current} -> {decision.target})"
        )
        print(f"  Reason: {decision.reason}")
        print(
            f"  CPU: {decision.cpu_percent:.1f}% | Memory: {decision.memory_percent:.1f}%"
        )
        time.sleep(6)

    monitor.stop()
    print("\\n\\nAutoscaler decision log:")
    for d in autoscaler._decisions:
        print(f"  {d.direction.value}: {d.current}->{d.target} ({d.reason})")
