"""
Prototype: gevent-compatible Ping using icmplib
=================================================
Replaces fping subprocess calls with icmplib for gevent compatibility.
"""

import time

GEVENT_AVAILABLE = False
try:
    from gevent import monkey

    monkey.patch_all()
    import gevent

    GEVENT_AVAILABLE = True
except ImportError:
    pass

from icmplib import ping as icmp_ping, multiping as icmp_multiping
from dataclasses import dataclass


@dataclass
class PingResult:
    reachable: int
    loss: float
    rtt_min: float
    rtt_avg: float
    rtt_max: float

    def to_dict(self) -> dict:
        return {
            "reachable": self.reachable,
            "loss": self.loss,
            "rtt_min": self.rtt_min,
            "rtt_avg": self.rtt_avg,
            "rtt_max": self.rtt_max,
        }


def ping_host(
    host: str,
    count: int = 5,
    interval: float = 0.025,
    timeout: float = 0.8,
    payload_size: int = 56,
    privileged: bool = False,
) -> PingResult:
    try:
        result = icmp_ping(
            host,
            count=count,
            interval=interval,
            timeout=timeout,
            payload_size=payload_size,
            privileged=privileged,
        )
        return PingResult(
            reachable=1 if result.is_alive else 0,
            loss=result.packet_loss * 100,
            rtt_min=result.min_rtt,
            rtt_avg=result.avg_rtt,
            rtt_max=result.max_rtt,
        )
    except Exception:
        return PingResult(
            reachable=0, loss=100.0, rtt_min=0.0, rtt_avg=0.0, rtt_max=0.0
        )


def ping_hosts_concurrent(
    hosts: list[str],
    count: int = 5,
    interval: float = 0.025,
    timeout: float = 0.8,
    privileged: bool = False,
) -> dict[str, PingResult]:
    if not GEVENT_AVAILABLE:
        return {host: ping_host(host, count, interval, timeout) for host in hosts}

    jobs = {
        host: gevent.spawn(ping_host, host, count, interval, timeout) for host in hosts
    }
    gevent.joinall(list(jobs.values()), timeout=timeout * count + 5)

    return {
        host: (
            job.value
            if job.value is not None
            else PingResult(
                reachable=0, loss=100.0, rtt_min=0.0, rtt_avg=0.0, rtt_max=0.0
            )
        )
        for host, job in jobs.items()
    }


def ping_hosts_multiping(
    hosts: list[str],
    count: int = 5,
    interval: float = 0.025,
    timeout: float = 0.8,
    privileged: bool = False,
) -> dict[str, PingResult]:
    try:
        results_list = icmp_multiping(
            hosts,
            count=count,
            interval=interval,
            timeout=timeout,
            privileged=privileged,
            concurrent_tasks=len(hosts),
        )
        return {
            r.address: PingResult(
                reachable=1 if r.is_alive else 0,
                loss=r.packet_loss * 100,
                rtt_min=r.min_rtt,
                rtt_avg=r.avg_rtt,
                rtt_max=r.max_rtt,
            )
            for r in results_list
        }
    except Exception:
        return {
            h: PingResult(
                reachable=0, loss=100.0, rtt_min=0.0, rtt_avg=0.0, rtt_max=0.0
            )
            for h in hosts
        }


OPENWISP_INTEGRATION_PATTERN = """
class Ping(BaseCheck):
    def check(self, store=True):
        ip = self._get_ip()
        config = self._get_config()

        from icmplib import ping
        result_raw = ping(
            ip,
            count=config.get('count', 5),
            interval=config.get('interval', 0.025),
            timeout=config.get('timeout', 0.8),
            payload_size=config.get('bytes', 56),
            privileged=False,
        )
        result = {
            'reachable': 1 if result_raw.is_alive else 0,
            'loss': result_raw.packet_loss * 100,
            'rtt_min': result_raw.min_rtt,
            'rtt_avg': result_raw.avg_rtt,
            'rtt_max': result_raw.max_rtt,
        }

        if store:
            self.timed_store(result)
        return result
"""

if __name__ == "__main__":
    print("icmplib Ping Prototype\n" + "=" * 50)
    print(f"gevent available: {GEVENT_AVAILABLE}")

    test_hosts = ["8.8.8.8", "1.1.1.1", "127.0.0.1"]

    print("\n--- Single host ping ---")
    for host in test_hosts:
        start = time.time()
        result = ping_host(host)
        elapsed = time.time() - start
        print(
            f"  {host}: reachable={result.reachable}, loss={result.loss:.1f}%, rtt_avg={result.rtt_avg:.2f}ms ({elapsed:.2f}s)"
        )

    print(f"\n--- Concurrent ping ({len(test_hosts)} hosts) ---")
    start = time.time()
    results = (
        ping_hosts_concurrent(test_hosts)
        if GEVENT_AVAILABLE
        else {h: ping_host(h) for h in test_hosts}
    )
    elapsed = time.time() - start

    for host, result in results.items():
        print(
            f"  {host}: reachable={result.reachable}, loss={result.loss:.1f}%, rtt_avg={result.rtt_avg:.2f}ms"
        )
    print(f"  Total time: {elapsed:.2f}s (concurrent)")

    print(f"\n--- icmplib multiping ({len(test_hosts)} hosts) ---")
    start = time.time()
    results = ping_hosts_multiping(test_hosts)
    elapsed = time.time() - start

    for host, result in results.items():
        print(
            f"  {host}: reachable={result.reachable}, loss={result.loss:.1f}%, rtt_avg={result.rtt_avg:.2f}ms"
        )
    print(f"  Total time: {elapsed:.2f}s (multiping)")
