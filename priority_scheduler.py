"""
Prototype: Priority Scheduler
===============================
Allocates execution slots across priority tiers with configurable
reserves, starvation prevention, and capacity borrowing.
"""

import random
import time
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from collections import deque
from threading import Lock

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class Priority(IntEnum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class PriorityTierConfig:
    priority: Priority
    reserve_percent: float
    min_slots: int = 1


@dataclass
class TierState:
    config: PriorityTierConfig
    reserved_slots: int = 0
    active_count: int = 0
    borrowed_count: int = 0
    total_executed: int = 0
    total_queued: int = 0
    _lock: Lock = field(default_factory=Lock)

    @property
    def available_own(self) -> int:
        return max(0, self.reserved_slots - self.active_count)

    @property
    def utilization(self) -> float:
        return self.active_count / self.reserved_slots if self.reserved_slots else 0.0


class PriorityScheduler:
    DEFAULT_TIERS = [
        PriorityTierConfig(Priority.CRITICAL, reserve_percent=20, min_slots=2),
        PriorityTierConfig(Priority.HIGH, reserve_percent=30, min_slots=2),
        PriorityTierConfig(Priority.NORMAL, reserve_percent=40, min_slots=2),
        PriorityTierConfig(Priority.LOW, reserve_percent=10, min_slots=1),
    ]

    def __init__(
        self,
        total_concurrency: int = 100,
        tier_configs: list[PriorityTierConfig] | None = None,
    ):
        self.total_concurrency = total_concurrency
        self._tier_configs = tier_configs or self.DEFAULT_TIERS
        self._lock = Lock()

        assert (
            abs(sum(t.reserve_percent for t in self._tier_configs) - 100.0) < 0.01
        ), "Reserve percentages must sum to 100"

        self.tiers: dict[Priority, TierState] = {}
        self._allocate_slots(total_concurrency)
        self._admission_log: deque = deque(maxlen=1000)

    def _allocate_slots(self, total: int):
        allocated = 0
        for config in sorted(self._tier_configs, key=lambda c: c.priority):
            slots = max(config.min_slots, int(total * config.reserve_percent / 100))
            allocated += slots
            if config.priority in self.tiers:
                self.tiers[config.priority].reserved_slots = slots
                self.tiers[config.priority].config = config
            else:
                self.tiers[config.priority] = TierState(
                    config=config, reserved_slots=slots
                )

        if Priority.NORMAL in self.tiers:
            self.tiers[Priority.NORMAL].reserved_slots += max(0, total - allocated)

        logger.info(
            "Allocated slots: %s",
            {p.name: self.tiers[p].reserved_slots for p in self.tiers},
        )

    def try_acquire(self, priority: Priority) -> bool:
        with self._lock:
            if not (tier := self.tiers.get(priority)):
                return False

            if tier.available_own > 0:
                tier.active_count += 1
                tier.total_executed += 1
                self._log_admission(priority, "own_reserve")
                return True

            for borrow_priority, borrow_tier in sorted(
                self.tiers.items(), reverse=True
            ):
                if borrow_priority <= priority:
                    continue
                if borrow_tier.available_own > borrow_tier.config.min_slots:
                    tier.active_count += 1
                    tier.borrowed_count += 1
                    tier.total_executed += 1
                    borrow_tier.reserved_slots -= 1
                    self._log_admission(
                        priority, f"borrowed_from_{Priority(borrow_priority).name}"
                    )
                    return True

            tier.total_queued += 1
            return False

    def release(self, priority: Priority):
        with self._lock:
            if not (tier := self.tiers.get(priority)):
                return

            tier.active_count -= 1
            if tier.borrowed_count > 0:
                tier.borrowed_count -= 1
                for return_priority in sorted(self.tiers.keys(), reverse=True):
                    if return_priority > priority:
                        self.tiers[return_priority].reserved_slots += 1
                        break

    def adjust_total_concurrency(self, new_total: int):
        with self._lock:
            old_total = self.total_concurrency
            self.total_concurrency = new_total
            self._allocate_slots(new_total)
            logger.info("Concurrency adjusted: %d -> %d", old_total, new_total)

    def get_stats(self) -> dict:
        with self._lock:
            return {
                Priority(priority).name: {
                    "reserved": tier.reserved_slots,
                    "active": tier.active_count,
                    "available": tier.available_own,
                    "utilization": f"{tier.utilization:.1%}",
                    "total_executed": tier.total_executed,
                    "total_queued": tier.total_queued,
                    "borrowed": tier.borrowed_count,
                }
                for priority, tier in self.tiers.items()
            }

    def _log_admission(self, priority: Priority, method: str):
        self._admission_log.append(
            {
                "priority": Priority(priority).name,
                "method": method,
                "timestamp": time.time(),
            }
        )


if __name__ == "__main__":
    scheduler = PriorityScheduler(total_concurrency=50)
    print("Priority Scheduler Prototype\n" + "=" * 50)
    print(f"\nInitial allocation (total={scheduler.total_concurrency}):")
    for name, stats in scheduler.get_stats().items():
        print(f"  {name}: {stats['reserved']} slots reserved")

    print("\n--- Simulating mixed workload ---")
    acquired = []
    task_mix = (
        [(Priority.CRITICAL, f"critical_{i}") for i in range(5)]
        + [(Priority.HIGH, f"high_{i}") for i in range(15)]
        + [(Priority.NORMAL, f"normal_{i}") for i in range(40)]
        + [(Priority.LOW, f"low_{i}") for i in range(10)]
    )
    random.shuffle(task_mix)

    for priority, task_id in task_mix:
        if scheduler.try_acquire(priority):
            acquired.append((priority, task_id))

    print(f"\\nAfter submitting {len(task_mix)} tasks:")
    for name, stats in scheduler.get_stats().items():
        print(
            f"  {name}: active={stats['active']}/{stats['reserved']} ({stats['utilization']}) | queued={stats['total_queued']} | borrowed={stats['borrowed']}"
        )

    print("\n--- Releasing 20 tasks, then checking CRITICAL availability ---")
    for priority, task_id in acquired[:20]:
        scheduler.release(priority)

    print(
        f"CRITICAL task admitted after releases: {scheduler.try_acquire(Priority.CRITICAL)}"
    )

    print("\n--- Autoscaler increases capacity to 100 ---")
    scheduler.adjust_total_concurrency(100)
    for name, stats in scheduler.get_stats().items():
        print(f"  {name}: {stats['reserved']} slots reserved")

    print("\\nDone.")
