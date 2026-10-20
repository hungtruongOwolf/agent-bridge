import pytest

from bridge.engine.tavily import MAX_RESULTS, SNIPPET, SearchError, TavilySearch, load_tavily_key


def fake_post(results, seen=None):
    def post(url, headers, body):
        if seen is not None:
            seen.update(url=url, headers=headers, body=body)
        return {"results": results}
    return post


def test_results_are_trimmed_and_limited():
    big = [{"title": "T" * 500, "url": "https://x.example/a", "content": "word " * 500, "raw_content": "SECRET" * 99}] * 6
    out = TavilySearch("K", post=fake_post(big)).search("saas trends")
    assert len(out) == MAX_RESULTS
    assert set(out[0]) == {"title", "url", "snippet"}  # raw_content never passes through
    assert len(out[0]["snippet"]) <= SNIPPET and len(out[0]["title"]) <= 120


def test_query_is_sent_cleaned_with_a_bearer_key():
    seen = {}
    TavilySearch("KEY1", post=fake_post([], seen)).search("  saas \n  trends  ")
    assert seen["body"]["query"] == "saas trends" and seen["headers"]["Authorization"] == "Bearer KEY1"


def test_empty_query_refused():
    with pytest.raises(SearchError, match="empty"):
        TavilySearch("K", post=fake_post([])).search("   ")


def test_failure_never_leaks_the_key():
    def boom(url, headers, body):
        raise RuntimeError("401 for Bearer SECRETKEY")

    with pytest.raises(SearchError) as e:
        TavilySearch("SECRETKEY", post=boom).search("x")
    assert "SECRETKEY" not in str(e.value) and "RuntimeError" in str(e.value)


def test_load_key(tmp_path):
    f = tmp_path / ".env"
    f.write_text("NEBIUS_API_KEY=n\nTAVILY_API_KEY=tvly-1\n", encoding="utf-8")
    assert load_tavily_key(f) == "tvly-1"
    with pytest.raises(SearchError):
        load_tavily_key(tmp_path / "absent.env")
    f.write_text("TAVILY_API_KEY=\n", encoding="utf-8")
    with pytest.raises(SearchError):
        load_tavily_key(f)
