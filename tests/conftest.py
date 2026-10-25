"""Pytest fixtures and mock objects for Justapedia Archiver Bot tests."""

import pytest
import tempfile
from pathlib import Path
from bot.database import Database


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    import gc
    import shutil

    temp_dir = tempfile.mkdtemp(prefix="test_db_")
    temp_path = str(Path(temp_dir) / "test.db")
    db = Database(temp_path)
    yield db

    # Release any lingering SQLite handles before directory removal
    gc.collect()
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture
def sample_article_wikitext():
    """Standard wikitext sample with diverse citation templates and edge cases."""
    return """{{Short description|Notable Researcher}}
{{Infobox person
| name = Jane Doe
| birth_date = 1970-01-01
}}
Jane Doe is a researcher who made significant contributions to physics.<ref>{{cite web |title=Physics Breakthrough |url=https://example.com/paper |date=2020-05-10 |access-date=2021-01-01}}</ref>

She previously wrote a news piece on energy.<ref>{{cite news
 |title=Clean Energy in 2018
 |url=https://example.org/energy
 |work=Daily Science
 |date=2018-09-15
}}</ref>

Another citation with existing archive:<ref>{{cite web |title=Archived Discovery |url=https://preserved.org/article |archive-url=https://web.archive.org/web/20190101120000/https://preserved.org/article |archive-date=2019-01-01 |url-status=live}}</ref>

Citation with only archive-url:<ref>{{cite web |title=Missing Date |url=https://half-archived.org/info |archive-url=https://web.archive.org/web/20210615102030/https://half-archived.org/info}}</ref>

Citation with nested template in title:<ref>{{cite web |url=https://foreign.org/noticia |title={{lang|es|La Gran Noticia}} |date=2015-11-20}}</ref>

== References ==
{{reflist}}

[[Category:Living people]]
[[Category:Physicists]]
"""
