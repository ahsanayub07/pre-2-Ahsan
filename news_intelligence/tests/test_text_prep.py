from text_prep import (build_model_text, domain_from_url, length_summary,
                       normalize_whitespace, percentile)


def test_domain_basic():
    assert domain_from_url("https://www.Example.com/a/b?x=1") == "example.com"


def test_domain_port_and_subdomain():
    assert domain_from_url("http://news.site.org:8080/x") == "news.site.org"


def test_domain_missing_or_bad():
    assert domain_from_url("") == ""
    assert domain_from_url(None) == ""
    assert domain_from_url("not a url") == ""
    assert domain_from_url("example.com/path") == ""


def test_domain_query_without_path():
    assert domain_from_url("https://a.com?x=1") == "a.com"


def test_whitespace():
    assert normalize_whitespace("  a \n\t b  ") == "a b"
    assert normalize_whitespace(None) == ""


def test_model_text_joins():
    assert build_model_text("Title", "Body text") == "Title. Body text"
    assert build_model_text("Why?", "Body") == "Why? Body"
    assert build_model_text("", " Body ") == "Body"
    assert build_model_text("Title", "") == "Title"
    assert build_model_text("", "") == ""


def test_percentile_and_summary():
    assert percentile([], 50) is None
    assert percentile([5], 99) == 5
    s = length_summary(list(range(1, 101)))
    assert s["count"] == 100 and s["min"] == 1 and s["max"] == 100
    assert s["median"] in (50, 51) and s["mean"] == 50.5
    assert length_summary([]) == {"count": 0}
