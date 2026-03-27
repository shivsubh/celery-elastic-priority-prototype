"""
Prototype: Resource Monitor
============================
Tracks CPU/memory and calculates safe worker capacity.
"""

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
import psutil

@dataclass
class ResourceSnapshot:
    cpu_percent: float
    memory_percent: float
    timestamp: float = field(default_factory=time.time)

@dataclass
class TaskResourceProfile:
    task_name: str
    sample_count: int = 0
    avg_cpu_delta: float = 0.0
    avg_memory_delta_mb: float = 0.0

    def update(self, cpu_delta: float, memory_delta_mb: float):
        self.sample_count += 1
        n = self.sample_count
        self.avg_cpu_delta += (cpu_delta - self.avg_cpu_delta) / n
        self.avg_memory_delta_mb += (memory_delta_mb - self.avg_memory_delta_mb) / n

class ResourceMonitor:
    def __init__(
        self,
        max_cpu_percent: float = 80.0,
        max_memory_percent: float = 85.0,
        max_concurrency: int | None = None,
        min_concurrency: int = 2,
        sample_interval: float = 2.0,
        ema_alpha: float = 0.3,
    ):
        self.max_cpu = max_cpu_percent
        self.max_memory = max_memory_percent
        self.max_concurrency = max_concurrency
        self.min_concurrency = min_concurrency
        self.sample_interval = sample_interval
        self.ema_alpha = ema_alpha

        self._ema_cpu: float | None = None
        self._ema_memory: float | None = None
        self._task_profiles: dict[str, TaskResourceProfile] = defaultdict(lambda: TaskResourceProfile(task_name="unknown"))
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._history: list[ResourceSnapshot] = []

        psutil.cpu_percent(interval=None)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _sample_loop(self):
        while self._running:
            self._take_sample()
            time.sleep(self.sample_interval)

    def _take_sample(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        with self._lock:
            if self._ema_cpu is None:
                self._ema_cpu = cpu
                self._ema_memory = mem
            else:
                self._ema_cpu = self.ema_alpha * cpu + (1 - self.ema_alpha) * self._ema_cpu
                self._ema_memory = self.ema_alpha * mem + (1 - self.ema_alpha) * self._ema_memory

            self._history.append(ResourceSnapshot(cpu_percent=cpu, memory_percent=mem))
            if len(self._history) > 100:
                self._history = self._history[-100:]

    @property
    def current_snapshot(self) -> ResourceSnapshot:
        with self._lock:
            return ResourceSnapshot(cpu_percent=self._ema_cpu or 0.0, memory_percent=self._ema_memory or 0.0)

    def get_available_capacity(self) -> int:
        self._take_sample()
        snap = self.current_snapshot

        cpu_headroom = max(0.0, self.max_cpu - snap.cpu_percent)
        mem_headroom = max(0.0, self.max_memory - snap.memory_percent)
        estimated_capacity = self._headroom_to_workers(cpu_headroom, mem_headroom)

        capacity = max(self.min_concurrency, estimated_capacity)
        if self.max_concurrency is not None:
            capacity = min(capacity, self.max_concurrency)

        return capacity

    def _headroom_to_workers(self, cpu_headroom: float, mem_headroom: float) -> int:
        return min(int(mem_headroom * 5), int(cpu_headroom * 2))

    def record_task_resources(self, task_name: str, cpu_delta: float, memory_delta_mb: float):
        with self._lock:
            profile = self._task_profiles[task_name]
            profile.task_name = task_name
            profile.update(cpu_delta, memory_delta_mb)

    def get_task_profile(self, task_name: str) -> TaskResourceProfile | None:
        with self._lock:
            return self._task_profiles.get(task_name)

    def is_healthy(self) -> bool:
        snap = self.current_snapshot
        return snap.cpu_percent < self.max_cpu and snap.memory_percent < self.max_memory

if __name__ == "__main__":
    monitor = ResourceMonitor(max_cpu_percent=80, max_memory_percent=85)
    monitor.start()

    print("Resource Monitor Prototype\\n" + "=" * 40)

    for i in range(5):
        time.sleep(2)
        snap = monitor.current_snapshot
        print(
            f"[Sample {i+1}] CPU: {snap.cpu_percent:.1f}% | "
            f"Memory: {snap.memory_percent:.1f}% | "
            f"Available capacity: {monitor.get_available_capacity()} workers | "
            f"Healthy: {monitor.is_healthy()}"
        )

    monitor.record_task_resources("perform_check", cpu_delta=0.5, memory_delta_mb=2.1)
    monitor.record_task_resources("perform_check", cpu_delta=0.3, memory_delta_mb=1.8)
    print(f"\\nTask profile for 'perform_check': {monitor.get_task_profile('perform_check')}")

    monitor.stop()
    print("\\nMonitor stopped.")
