import subprocess
from icmplib import ping
from celery import Celery

app = Celery(
    "sample_gevent_app",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "sample_app.fast_io_task": {"queue": "monitoring"},
        "sample_app.slow_blocking_task": {"queue": "default"},
    },
)


PING_COUNT = 2
PING_INTERVAL = 0.1
PING_TIMEOUT = 0.8  # Consistent timeout for both tasks
PING_IP = "8.8.8.8"  # Common IP for both


@app.task(bind=True)
def fast_io_task(self, task_id):
    """
    Simulates a fast I/O bound task using icmplib to ping a public IP.
    Since gevent patches the socket library, icmplib's UDP sockets will yield control to other greenlets.
    """
    print(f"[fast_io_task] Task {task_id} started (Pinging {PING_IP} with icmplib)")
    try:
        result = ping(
            PING_IP,
            count=PING_COUNT,
            interval=PING_INTERVAL,
            timeout=PING_TIMEOUT,
            privileged=False,
        )
        output = f"reachable: {result.is_alive}, avg_rtt: {result.avg_rtt}ms, loss: {result.packet_loss*100}%"
    except Exception as e:
        output = str(e)
    print(f"[fast_io_task] Task {task_id} completed!")
    return f"fast_io_task_{task_id}_success -> {PING_IP} ({output})"


@app.task(bind=True)
def slow_blocking_task(self, task_id):
    """
    Simulates a blocking CPU-bound or native-library task using fping subprocess.
    If run in a gevent pool, the subprocess block would BLOCK the entire worker!
    Therefore, this belongs in a thread/prefork pool 'default' queue.
    """
    print(f"[slow_blocking_task] Task {task_id} started (Pinging {PING_IP} with fping)")
    try:
        # Blocking subprocess call
        timeout_ms = str(int(PING_TIMEOUT * 1000))
        interval_ms = str(int(PING_INTERVAL * 1000))
        result = subprocess.run(
            [
                "fping",
                "-c",
                str(PING_COUNT),
                "-p",
                interval_ms,
                "-t",
                timeout_ms,
                PING_IP,
            ],
            capture_output=True,
            text=True,
        )
        # Process output to get a readable string
        output = (
            result.stderr.strip().split("\n")[-1]
            if result.stderr
            else result.stdout.strip()
        )
    except Exception as e:
        output = str(e)
    print(f"[slow_blocking_task] Task {task_id} completed!")
    return f"slow_blocking_task_{task_id}_success -> {PING_IP} ({output})"
