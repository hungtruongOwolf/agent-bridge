from bridge.engine.mask import Masker


def test_contact_details_are_swapped_and_restored():
    m = Masker()
    src = {"id": "rec_123456789012", "text": "Call Dana on (415) 555-0134 or +1 415 555 0134, mail dana.k@acme.example. Account 000111222333.",
           "when": "2026-10-21 10:30", "n": 7}
    out = m.mask(src)
    t = out["text"]
    assert "dana.k@acme.example" not in t and "555-0134" not in t and "000111222333" not in t
    assert "[EMAIL_1]" in t and "[PHONE_1]" in t and "[NUMBER_1]" in t
    assert out["id"] == src["id"] and out["when"] == src["when"] and out["n"] == 7   # ids, dates and plain numbers are left alone
    assert m.unmask({"a": ["mail [EMAIL_1] or EMAIL_1", "[PHONE_1]"]}) == {"a": ["mail dana.k@acme.example or dana.k@acme.example", "(415) 555-0134"]}


def test_same_value_same_placeholder_across_calls_and_unknown_placeholders_stay():
    m = Masker()
    a = m.mask("x@y.example and x@y.example")
    assert a == "[EMAIL_1] and [EMAIL_1]" and m.last["EMAIL"] == 2
    assert m.mask("again x@y.example") == "again [EMAIL_1]"
    assert m.unmask("[EMAIL_9]") == "[EMAIL_9]"
