import json
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "docs" / "postman"


def test_postman_files_parse_and_hold_no_secrets():
    col = json.loads((D / "agora-paypal-sandbox.postman_collection.json").read_text(encoding="utf-8"))
    env = json.loads((D / "agora-paypal-sandbox.postman_environment.json").read_text(encoding="utf-8"))
    assert len(col["item"]) == 8 and all(i["request"] for i in col["item"])
    vals = {v["key"]: v for v in env["values"]}
    for k in ("client_id", "client_secret", "access_token", "order_id", "authorization_id", "capture_id", "payout_batch_id"):
        assert vals[k]["value"] == ""
    assert vals["client_secret"]["type"] == "secret"
    assert "api-m.sandbox.paypal.com" in vals["base_url"]["value"]
