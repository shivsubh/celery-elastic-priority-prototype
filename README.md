# Celery Elastic Priority Prototype

This repository contains proof-of-concept prototypes. The actual implementation in the final project might be different. These scripts are designed purely to validate and demonstrate various patterns such as Gevent-Celery integration, dynamic priority-based task scheduling, and resource-based autoscaling.

## Files and Use Cases

- **`priority_scheduler.py`**
  A structural prototype demonstrating elastic priority queue allocation. It defines queues with different priority tiers (CRITICAL, HIGH, NORMAL, LOW) and simulates task admissions, backlog queuing, and runtime concurrency readjustments.
  *How to run:* `python priority_scheduler.py`

- **`resource_autoscaler.py`**
  Simulates a monitoring loop that dynamically adjusts the total concurrency pool based on real-time resource utilization (CPU/Memory). It relies on the Priority Scheduler and Resource Monitor.
  *How to run:* `python resource_autoscaler.py`

- **`resource_monitor.py`**
  A utility providing OS-level resource monitoring (current CPU and memory usage) which is used to feed utilization metrics to the autoscaler.
  *How to run:* `python resource_monitor.py`

- **`sample_app.py`**
  A minimalistic Celery application configured to use Redis as a broker. It defines two sample Celery tasks:
  - `fast_io_task` (routed to the `monitoring` queue): Uses the `icmplib` python library to send an ICMP ping to a random public IP address, simulating a fast, non-blocking I/O operation.
  - `slow_blocking_task` (routed to the `default` queue): Uses the `fping` executable via a subprocess to ping a random public IP address, simulating a blocking or native library operation.

- **`run_sample.py`**
  Submits the sample tasks to the Celery workers and waits for their aggregated results, demonstrating how the gevent pool handles concurrent fast I/O tasks efficiently vs blocking tasks.
  *How to run:* `python run_sample.py` (Ensure Celery workers and Redis are running first)

- **`icmplib_ping.py`**
  A discrete prototype used to test network pinging capabilities using the `icmplib` library (testing non-blocking or asynchronous ICMP request capabilities).
  *How to run:* `sudo python icmplib_ping.py` (May require root privileges for ICMP sockets)

- **`benchmark_harness.py`**
  A utility harness designed to stress-test or benchmark task processing performance and throughput under load.
  *How to run:* `python benchmark_harness.py`

## Running the Celery Worker Sample

To test the actual Celery processing flow defined in `sample_app.py`:

1. Ensure a local **Redis** server is running and accessible on `localhost:6379`.
2. Start the gevent pool worker for fast I/O tasks:
   ```bash
   celery -A sample_app worker -Q monitoring -P gevent -c 100 --loglevel=info
   ```
3. Start the thread pool worker for blocking tasks:
   ```bash
   celery -A sample_app worker -Q default -P threads -c 4 --loglevel=info
   ```
4. Execute the submitter script to trigger tasks:
   ```bash
   python run_sample.py
   ```

## OpenWISP Monitoring Integration

The prototype concepts have actively been integrated into the local `openwisp-monitoring` repository clone:

1. **Gevent Decorators (`openwisp_monitoring/celery_utils.py`)**:
   - Introduced `@gevent_safe` and `@blocking` task decorators.
   - These decorators explicitly explicitly tag the underlying workload so that I/O bound tasks and blocking tasks are auditable.
2. **Task Routing (`openwisp_monitoring/settings.py`)**:
   - Added `CELERY_TASK_ROUTES` defaulting the fast network I/O tasks (`perform_check`, `run_checks`, `timeseries_write`, etc.) to the `monitoring` queue.
3. **Annotated Tasks**:
   - `check/tasks.py`: `run_checks`, `perform_check` mapped to `@gevent_safe`. `auto_create_check` mapped to `@blocking`.
   - `monitoring/tasks.py`: TSDB networking tasks (`timeseries_write`, `timeseries_batch_write`) mapped to `@gevent_safe`. DB restructuring/deletions mapped to `@blocking`.
   - `device/tasks.py`: Heavy DB deletions mapped to `@blocking`. Fast writers/dispatchers mapped to `@gevent_safe`.
