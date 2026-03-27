from django.conf import settings


def get_settings_value(option, default=None):
    return getattr(settings, f"OPENWISP_MONITORING_{option}", default)


AUTO_CHARTS = get_settings_value(
    "AUTO_CHARTS",
    (
        "traffic",
        "wifi_clients",
        "uptime",
        "packet_loss",
        "rtt",
        "memory",
        "cpu",
        "disk",
    ),
)

MONITORING_API_URLCONF = get_settings_value("API_URLCONF", None)
MONITORING_API_BASEURL = get_settings_value("API_BASEURL", None)
MONITORING_TIMESERIES_RETRY_OPTIONS = get_settings_value(
    "TIMESERIES_RETRY_OPTIONS", dict(max_retries=6, delay=2)
)
CACHE_TIMEOUT = get_settings_value(
    "CACHE_TIMEOUT",
    24 * 60 * 60,  # 24 hours in seconds
)
DEFAULT_CHART_TIME = get_settings_value("DEFAULT_CHART_TIME", "7d")

CELERY_TASK_ROUTES = get_settings_value(
    "CELERY_TASK_ROUTES",
    {
        "openwisp_monitoring.check.tasks.perform_check": {"queue": "monitoring"},
        "openwisp_monitoring.check.tasks.run_checks": {"queue": "monitoring"},
        "openwisp_monitoring.monitoring.tasks.timeseries_write": {"queue": "monitoring"},
        "openwisp_monitoring.monitoring.tasks.timeseries_batch_write": {"queue": "monitoring"},
        "openwisp_monitoring.device.tasks.write_device_metrics": {"queue": "monitoring"},
    },
)
