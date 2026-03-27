from sample_app import fast_io_task, slow_blocking_task
import time


def run():
    print("Submitting 5 fast I/O tasks to 'monitoring' queue (gevent bound)...")
    fast_results = []
    start = time.time()

    for i in range(5):
        result = fast_io_task.apply_async(args=[i], queue="monitoring")
        fast_results.append((i, result))

    print("Tasks submitted. Waiting for results...")

    for i, res in fast_results:
        print(f"Result for fast I/O task {i}: {res.get(timeout=10)}")

    total_time = time.time() - start
    print(f"All fast I/O tasks completed in {total_time:.2f} seconds.")

    print("\n------------------------------------------------\n")

    print("Now submitting 2 slow blocking tasks to 'default' queue (thread bound)...")
    slow_results = []
    start = time.time()
    for i in range(5):
        result = slow_blocking_task.apply_async(args=[i], queue="default")
        slow_results.append((i, result))

    print("Tasks submitted. Waiting for results...")

    for i, res in slow_results:
        print(f"Result for slow blocking task {i}: {res.get(timeout=10)}")

    total_time = time.time() - start
    print(f"All slow blocking tasks completed in {total_time:.2f} seconds.")


if __name__ == "__main__":
    run()
