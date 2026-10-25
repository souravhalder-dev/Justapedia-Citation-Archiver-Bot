"""Unit tests for SQLite database and persistent caching layer."""

from bot.database import Database


def test_url_cache_lifecycle(temp_db):
    temp_db.set_url_cache("https://test.com", "working", 200, "https://test.com")
    cached = temp_db.get_url_cache("https://test.com", ttl_days=14)
    assert cached is not None
    assert cached["status"] == "working"
    assert cached["http_code"] == 200

    # Non-existent
    assert temp_db.get_url_cache("https://notfound.com") is None


def test_snapshot_cache_lifecycle(temp_db):
    temp_db.set_snapshot_cache(
        url="https://test.com",
        snapshot_url="https://web.archive.org/web/20200101/https://test.com",
        snapshot_date="2020-01-01",
        timestamp="20200101000000",
        source_api="availability",
    )
    cached = temp_db.get_snapshot_cache("https://test.com")
    assert cached is not None
    assert cached["timestamp"] == "20200101000000"
    assert cached["source_api"] == "availability"


def test_job_and_checkpoint_tracking(temp_db):
    temp_db.create_job("job-123", "article", "Test Article", mode="dry_run")
    temp_db.record_job_article("job-123", "Test Article", "updated", 2, 1, "diff_text", "Updated 1")

    processed = temp_db.get_processed_articles_for_job("job-123")
    assert "Test Article" in processed

    stats = temp_db.get_stats()
    assert stats["total_jobs"] >= 1
    assert stats["articles_processed"] >= 1
