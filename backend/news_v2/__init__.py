"""
News v2 — pre-fetch & cache architecture for the stock-page news tab.

Entry points:
  - news_v2.api.router  — FastAPI router (mounted at /v2/news)
  - news_v2.celery_app.celery_app — Celery worker entrypoint
  - news_v2.scheduler.start_scheduler — APScheduler bootstrap
"""

__all__ = ["config", "service", "api"]
