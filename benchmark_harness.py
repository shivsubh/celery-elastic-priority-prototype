"""
Prototype: Benchmark Harness
==============================
Framework for measuring and comparing performance of:
- Multi-worker (current) vs priority-scheduled (new) architecture
- gevent vs thread pool
- fping vs icmplib
"""

import random
import time
import statistics
from dataclasses import dataclass, field
from contextlib import contextmanager
from collections import defaultdict


@dataclass
class TaskMetric:
    task_name: str
    priority: str
    start_time: float
    end_time: float
    queue_time: float
    exec_time: float
    success: bool
    pool_type: str

    @property
    def total_latency(self) -> float:
        return self.queue_time + self.exec_time


@dataclass
class BenchmarkResult:
    scenario: str
    pool_type: str
    total_tasks: int
    duration_seconds: float
    metrics: list[TaskMetric] = field(default_factory=list)

    @property
    def throughput(self) -> float:
        return (
            self.total_tasks / self.duration_seconds if self.duration_seconds > 0 else 0
        )

    @property
    def avg_latency(self) -> float:
        latencies = [m.total_latency for m in self.metrics]
        return statistics.mean(latencies) if latencies else 0

    @property
    def p50_latency(self) -> float:
        latencies = sorted(m.total_latency for m in self.metrics)
        return latencies[len(latencies) // 2] if latencies else 0

    @property
    def p95_latency(self) -> float:
        latencies = sorted(m.total_latency for m in self.metrics)
        return latencies[int(len(latencies) * 0.95)] if latencies else 0

    @property
    def p99_latency(self) -> float:
        latencies = sorted(m.total_latency for m in self.metrics)
        return latencies[int(len(latencies) * 0.99)] if latencies else 0

    @property
    def success_rate(self) -> float:
        return (
            (sum(1 for m in self.metrics if m.success) / len(self.metrics) * 100)
            if self.metrics
            else 0
        )

    def latency_by_priority(self) -> dict[str, dict]:
        by_priority = defaultdict(list)
        for m in self.metrics:
            by_priority[m.priority].append(m.total_latency)

        return {
            priority: {
                "count": len(latencies),
                "avg": statistics.mean(latencies),
                "p50": sorted(latencies)[len(latencies) // 2],
                "p95": sorted(latencies)[int(len(latencies) * 0.95)],
                "max": max(latencies),
            }
            for priority, latencies in sorted(by_priority.items())
        }


class BenchmarkHarness:
    def __init__(self):
        self.results: list[BenchmarkResult] = []

    @contextmanager
    def benchmark_run(self, scenario: str, pool_type: str, total_tasks: int):
        result = BenchmarkResult(
            scenario=scenario,
            pool_type=pool_type,
            total_tasks=total_tasks,
            duration_seconds=0,
        )
        start = time.time()
        yield result
        result.duration_seconds = time.time() - start
        self.results.append(result)

    def compare(self, baseline_name: str, candidate_name: str) -> str:
        baseline = next((r for r in self.results if r.scenario == baseline_name), None)
        candidate = next(
            (r for r in self.results if r.scenario == candidate_name), None
        )

        if not baseline or not candidate:
            return "Missing scenario results for comparison"

        lines = [
            f"\n{'='*65}",
            f"BENCHMARK COMPARISON: {baseline_name} vs {candidate_name}",
            f"{'='*65}",
            f"\n{'Metric':<30} {'Baseline':>15} {'Candidate':>15}",
            f"{'-'*60}",
            f"{'Throughput (tasks/s)':<30} {baseline.throughput:>15.1f} {candidate.throughput:>15.1f}",
            f"{'Avg Latency (ms)':<30} {baseline.avg_latency*1000:>15.1f} {candidate.avg_latency*1000:>15.1f}",
            f"{'P50 Latency (ms)':<30} {baseline.p50_latency*1000:>15.1f} {candidate.p50_latency*1000:>15.1f}",
            f"{'P95 Latency (ms)':<30} {baseline.p95_latency*1000:>15.1f} {candidate.p95_latency*1000:>15.1f}",
            f"{'P99 Latency (ms)':<30} {baseline.p99_latency*1000:>15.1f} {candidate.p99_latency*1000:>15.1f}",
            f"{'Success Rate (%)':<30} {baseline.success_rate:>15.1f} {candidate.success_rate:>15.1f}",
            f"\n--- Latency by Priority (ms) ---",
        ]

        baseline_bp = baseline.latency_by_priority()
        candidate_bp = candidate.latency_by_priority()
        all_priorities = sorted(set(baseline_bp) | set(candidate_bp))

        for priority in all_priorities:
            b = baseline_bp.get(priority, {})
            c = candidate_bp.get(priority, {})
            lines.extend(
                [
                    f"\n  {priority.upper()}:",
                    f"    {'Avg':<10} {b.get('avg', 0)*1000:>10.1f}  ->  {c.get('avg', 0)*1000:>10.1f}",
                    f"    {'P95':<10} {b.get('p95', 0)*1000:>10.1f}  ->  {c.get('p95', 0)*1000:>10.1f}",
                    f"    {'Count':<10} {b.get('count', 0):>10}  ->  {c.get('count', 0):>10}",
                ]
            )

        if baseline.throughput > 0:
            lines.extend(
                [
                    f"\n--- Summary ---",
                    f"Throughput change: {((candidate.throughput - baseline.throughput) / baseline.throughput * 100):+.1f}%",
                ]
            )

        if baseline.avg_latency > 0:
            lines.append(
                f"Avg latency change: {((candidate.avg_latency - baseline.avg_latency) / baseline.avg_latency * 100):+.1f}%"
            )

        return "\n".join(lines)


if __name__ == "__main__":
    harness = BenchmarkHarness()
    priorities = ["critical", "high", "normal", "low"]
    weights = [5, 15, 60, 20]

    def simulate_tasks(result, pool_type, priority_latency_factor):
        for i in range(result.total_tasks):
            priority = random.choices(priorities, weights=weights, k=1)[0]
            factor = priority_latency_factor.get(priority, 1.0)
            queue_time = random.expovariate(1.0 / (0.05 * factor))
            exec_time = random.expovariate(1.0 / 0.1)
            result.metrics.append(
                TaskMetric(
                    task_name=f"perform_check_{i}",
                    priority=priority,
                    start_time=time.time(),
                    end_time=time.time() + queue_time + exec_time,
                    queue_time=queue_time,
                    exec_time=exec_time,
                    success=random.random() > 0.02,
                    pool_type=pool_type,
                )
            )

    with harness.benchmark_run("multi-worker-baseline", "thread", 1000) as result:
        simulate_tasks(
            result, "thread", {"critical": 1.0, "high": 1.0, "normal": 1.0, "low": 1.0}
        )

    with harness.benchmark_run("priority-gevent", "gevent", 1000) as result:
        simulate_tasks(
            result, "gevent", {"critical": 0.3, "high": 0.5, "normal": 1.0, "low": 1.5}
        )

    print(harness.compare("multi-worker-baseline", "priority-gevent"))
