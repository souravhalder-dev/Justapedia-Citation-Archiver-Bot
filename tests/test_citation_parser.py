"""Unit tests for citation parser and template classification."""

import pytest
from bot.citation_parser import CitationParser


def test_parse_citation_without_archive():
    wikitext = "{{cite web |title=Test Article |url=https://example.com/test |date=2020-01-01}}"
    citations = CitationParser.parse_citations(wikitext)
    assert len(citations) == 1
    c = citations[0]
    assert c.template_name == "cite web"
    assert c.url == "https://example.com/test"
    assert c.archive_url is None
    assert c.archive_date is None
    assert c.case == 1
    assert not c.has_archive


def test_parse_citation_with_existing_archive():
    wikitext = (
        "{{cite web |title=Archived Page |url=https://example.com/archived "
        "|archive-url=https://web.archive.org/web/20200101000000/https://example.com/archived "
        "|archive-date=2020-01-01 |url-status=live}}"
    )
    citations = CitationParser.parse_citations(wikitext)
    assert len(citations) == 1
    c = citations[0]
    assert c.has_archive
    assert c.case == 5
    assert c.archive_url == "https://web.archive.org/web/20200101000000/https://example.com/archived"
    assert c.archive_date == "2020-01-01"


def test_parse_citation_with_only_archive_url():
    wikitext = (
        "{{cite news |title=News Piece |url=https://news.com/item "
        "|archive-url=https://web.archive.org/web/20190505120000/https://news.com/item}}"
    )
    citations = CitationParser.parse_citations(wikitext)
    assert len(citations) == 1
    c = citations[0]
    assert c.case == 2
    assert c.archive_url is not None
    assert c.archive_date is None


def test_parse_citation_with_only_archive_date():
    wikitext = "{{cite journal |title=Journal Item |url=https://doi.org/123 |archive-date=2018-05-01}}"
    citations = CitationParser.parse_citations(wikitext)
    assert len(citations) == 1
    c = citations[0]
    assert c.case == 2
    assert c.archive_url is None
    assert c.archive_date == "2018-05-01"


def test_nested_templates_inside_citation():
    wikitext = (
        "<ref>{{cite web |url=https://spanish.org/art |title={{lang|es|Hola Mundo}} |date=2021-02-02}}</ref>"
    )
    citations = CitationParser.parse_citations(wikitext)
    assert len(citations) == 1
    c = citations[0]
    assert c.url == "https://spanish.org/art"
    assert "Hola Mundo" in str(c.title)


def test_ignore_internal_wikilinks():
    wikitext = "See also [[Main Page]] and [[Category:Help]] and {{other template|param=value}}"
    citations = CitationParser.parse_citations(wikitext)
    assert len(citations) == 0


def test_supported_template_variations():
    wikitext = """
    {{cite news |url=https://news.org |title=News}}
    {{cite journal |url=https://journal.org |title=Journal}}
    {{cite magazine |url=https://mag.org |title=Magazine}}
    {{citation |url=https://citation.org |title=General}}
    """
    citations = CitationParser.parse_citations(wikitext)
    assert len(citations) == 4
    names = [c.template_name for c in citations]
    assert "cite news" in names
    assert "cite journal" in names
    assert "cite magazine" in names
    assert "citation" in names


def test_duplicate_parameter_handling():
    # Wikitext with duplicate url parameter (last one wins in CS1)
    wikitext = "{{cite web |title=Dupe |url=https://first.com |url=https://second.com}}"
    citations = CitationParser.parse_citations(wikitext)
    assert len(citations) == 1
    # mwparserfromhell template.has('url') returns true
    assert citations[0].url in ("https://first.com", "https://second.com")
