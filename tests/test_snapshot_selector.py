"""Unit tests for snapshot selector and date parsing/formatting."""

from bot.archive_client import ArchiveSnapshot
from bot.snapshot_selector import SnapshotSelector


def test_parse_dates_to_timestamp():
    assert SnapshotSelector.parse_citation_date_to_timestamp("2020-05-10") == "20200510"
    assert SnapshotSelector.parse_citation_date_to_timestamp("May 10, 2020") == "20200510"
    assert SnapshotSelector.parse_citation_date_to_timestamp("10 May 2020") == "20200510"
    assert SnapshotSelector.parse_citation_date_to_timestamp("2018") == "20180101"
    assert SnapshotSelector.parse_citation_date_to_timestamp("") is None


def test_detect_date_style():
    assert SnapshotSelector.detect_date_style("2020-05-10") == "iso"
    assert SnapshotSelector.detect_date_style("May 10, 2020") == "mdy"
    assert SnapshotSelector.detect_date_style("10 May 2020") == "dmy"


def test_format_timestamp_to_date():
    ts = "20200510123045"
    assert SnapshotSelector.format_timestamp_to_date(ts, "iso") == "2020-05-10"
    assert SnapshotSelector.format_timestamp_to_date(ts, "mdy") == "May 10, 2020"
    assert SnapshotSelector.format_timestamp_to_date(ts, "dmy") == "10 May 2020"


def test_extract_timestamp_from_wayback_url():
    url = "https://web.archive.org/web/20210615102030/https://example.com/article"
    extracted = SnapshotSelector.extract_timestamp_and_url_from_archive_url(url)
    assert extracted is not None
    ts, orig = extracted
    assert ts == "20210615102030"
    assert orig == "https://example.com/article"


def test_select_best_snapshot_by_date_proximity():
    snap_early = ArchiveSnapshot("https://ex.com", "https://web.archive.org/web/20170101000000/https://ex.com", "20170101000000", 200)
    snap_close = ArchiveSnapshot("https://ex.com", "https://web.archive.org/web/20200512000000/https://ex.com", "20200512000000", 200)
    snap_late = ArchiveSnapshot("https://ex.com", "https://web.archive.org/web/20230101000000/https://ex.com", "20230101000000", 200)

    # Target: 2020-05-10
    target_ts = "20200510"
    selected = SnapshotSelector.select_best_snapshot(
        [snap_early, snap_late, snap_close],
        "https://ex.com",
        target_timestamp=target_ts,
    )
    assert selected == snap_close
