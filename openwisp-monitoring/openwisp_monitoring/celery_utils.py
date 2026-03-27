import warnings

_GEVENT_SAFE_TASKS = set()
_BLOCKING_TASKS = set()


def gevent_safe(func=None, *, reason=None):
    def decorator(f):
        _GEVENT_SAFE_TASKS.add(getattr(f, "name", f.__name__))
        f._gevent_safe = True
        f._gevent_safe_reason = reason
        return f

    return decorator(func) if func else decorator


def blocking(func=None, *, reason=None):
    def decorator(f):
        _BLOCKING_TASKS.add(getattr(f, "name", f.__name__))
        f._gevent_safe = False
        f._blocking_reason = reason
        return f

    return decorator(func) if func else decorator


def validate_task_routing(app):
    routes = app.conf.task_routes or {}
    gevent_queues = {"monitoring"}

    for task_name in _BLOCKING_TASKS:
        queue = routes.get(task_name, {}).get("queue", "default")
        if queue in gevent_queues:
            warnings.warn(
                f"Blocking task '{task_name}' is routed to gevent queue '{queue}'. "
                f"Reason marked blocking: {getattr(task_name, '_blocking_reason', 'unknown')}",
                RuntimeWarning,
            )
