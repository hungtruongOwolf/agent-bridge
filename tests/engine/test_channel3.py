import io
import socket
import urllib.error

import pytest

from bridge.engine.channel3 import (LIMIT, MAX_PRODUCTS, RECORDED_LABEL, Channel3Error, Channel3Search, RecordedProducts, WebTools,
                                    load_channel3_key, product_source)

DOC_PRODUCT = {  # shaped like the official docs' Search Response example
    "id": "prod_1", "title": "Example Canvas Tote", "brands": [{"id": "b1", "name": "Example Brand"}],
    "offers": [
        {"url": "https://pricey.example/tote", "domain": "pricey.example", "price": {"price": 49.0, "currency": "USD"}, "availability": "InStock"},
        {"url": "https://cheap.example/tote", "domain": "cheap.example", "price": {"price": 39.0, "compare_at_price": 49.0, "currency": "USD"}, "availability": "InStock"},
        {"url": "https://gone.example/tote", "domain": "gone.example", "price": {"price": 10.0, "currency": "USD"}, "availability": "OutOfStock"},
    ],
}


def post_returning(out, seen=None):
    def post(url, headers, body):
        if seen is not None:
            seen.update(url=url, headers=headers, body=body)
        return out
    return post


def test_success_is_normalized_to_the_cheapest_offer_in_stock():
    seen = {}
    out = Channel3Search("KEY1", post=post_returning({"products": [DOC_PRODUCT], "next_page_token": None}, seen)).search("  canvas \n tote ")
    assert out == [{"title": "Example Canvas Tote", "brand": "Example Brand", "price": 39.0, "currency": "USD", "availability": "InStock",
                    "merchant": "cheap.example", "url": "https://cheap.example/tote", "source": "Channel3"}]
    assert seen["url"] == "https://api.trychannel3.com/v1/search"
    assert seen["headers"]["x-api-key"] == "KEY1" and seen["body"] == {"query": "canvas tote", "limit": LIMIT}


def test_empty_result_is_an_empty_list_and_empty_query_is_refused():
    assert Channel3Search("K", post=post_returning({"products": []})).search("unicorn saddle") == []
    with pytest.raises(Channel3Error, match="nothing to search"):
        Channel3Search("K", post=post_returning({"products": []})).search("   ")


def test_product_without_offers_is_dropped():
    assert Channel3Search("K", post=post_returning({"products": [{"title": "x", "offers": []}]})).search("x") == []


def raising(exc):
    def post(url, headers, body):
        raise exc
    return post


@pytest.mark.parametrize("exc,words", [
    (urllib.error.HTTPError("u", 401, "no", {}, None), "did not accept the key"),
    (urllib.error.HTTPError("u", 402, "no", {}, None), "used up"),
    (urllib.error.HTTPError("u", 429, "no", {}, None), "too many"),
    (urllib.error.HTTPError("u", 500, "no", {}, None), "HTTP 500"),
    (socket.timeout("slow"), "took too long"),
    (urllib.error.URLError(socket.timeout()), "took too long"),
    (urllib.error.URLError("dns"), "could not be reached"),
])
def test_errors_become_plain_sentences_without_the_key(exc, words):
    with pytest.raises(Channel3Error) as e:
        Channel3Search("SECRETKEY", post=raising(exc)).search("x")
    assert words in str(e.value) and "SECRETKEY" not in str(e.value)


def test_unreadable_reply_is_a_plain_error():
    with pytest.raises(Channel3Error, match="not readable"):
        Channel3Search("K", post=post_returning({"products": "oops"})).search("x")
    with pytest.raises(Channel3Error):
        Channel3Search("K", post=post_returning({"nope": 1})).search("x")


def test_oversized_reply_is_trimmed():
    many = [{"title": "T" * 900, "brands": [{"name": "B" * 900}],
             "offers": [{"url": "https://x.example/" + "a" * 900, "domain": "d" * 500, "price": {"price": 1.234, "currency": "USDXXXXXXXXXXXX"}, "availability": "InStock"}]}] * 60
    out = Channel3Search("K", post=post_returning({"products": many})).search("x")
    assert len(out) == MAX_PRODUCTS
    p = out[0]
    assert len(p["title"]) <= 120 and len(p["brand"]) <= 60 and len(p["url"]) <= 300 and len(p["merchant"]) <= 80 and len(p["currency"]) <= 8
    assert set(p) == {"title", "brand", "price", "currency", "availability", "merchant", "url", "source"}


def test_default_transport_refuses_an_oversized_body(monkeypatch):
    from bridge.engine import channel3 as c3

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(c3.urllib.request, "urlopen", lambda req, timeout: Resp(b"x" * (c3.MAX_RESPONSE_BYTES + 5)))
    with pytest.raises(Channel3Error, match="more data"):
        Channel3Search("K").search("x")


def test_key_comes_from_the_environment_or_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("CHANNEL3_API_KEY", raising=False)
    f = tmp_path / ".env"
    with pytest.raises(Channel3Error):
        load_channel3_key(f)
    f.write_text("OTHER=1\nCHANNEL3_API_KEY=filekey\n", encoding="utf-8")
    assert load_channel3_key(f) == "filekey"
    monkeypatch.setenv("CHANNEL3_API_KEY", "envkey")
    assert load_channel3_key(f) == "envkey"


def test_recorded_source_is_labelled_and_used_when_there_is_no_key(tmp_path, monkeypatch):
    monkeypatch.delenv("CHANNEL3_API_KEY", raising=False)
    src = product_source(tmp_path / "missing.env")
    assert isinstance(src, RecordedProducts)
    out = src.search("a backpack for hiking, budget 80 dollars")
    assert out and all(p["source"] == RECORDED_LABEL and p["merchant"].endswith(".example") for p in out)
    assert src.search("saddle for a unicorn") == []
    monkeypatch.setenv("CHANNEL3_API_KEY", "k")
    assert isinstance(product_source(tmp_path / "missing.env"), Channel3Search)


def test_web_tools_routes_each_door():
    class S:
        def search(self, q):
            return ["page"]

    w = WebTools(S(), RecordedProducts())
    assert w.search("x") == ["page"] and w.product_search("backpack")
    with pytest.raises(Channel3Error):
        WebTools(S()).product_search("x")
