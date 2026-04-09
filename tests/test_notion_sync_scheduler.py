"""Tests for the Notion sync scheduler configuration."""
from backend.services.notion_sync.sync import make_scheduler


def test_scheduler_job_has_misfire_grace_time():
    """The notion_sync job must tolerate delayed execution (not skip on slight delay)."""
    scheduler = make_scheduler(notion_sync_hour=6)
    jobs = scheduler.get_jobs()
    assert len(jobs) == 1, "Expected exactly one scheduled job"
    job = jobs[0]
    assert job.id == "notion_sync"
    grace_time = getattr(job, "misfire_grace_time", None)
    assert grace_time is not None and grace_time >= 300, (
        f"misfire_grace_time={grace_time!r}; "
        "APScheduler will skip the job if it fires even slightly late — "
        "set misfire_grace_time=300 (5 min) to tolerate normal event loop jitter"
    )
