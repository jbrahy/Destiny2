from urllib.parse import parse_qs, urlparse

from app.bungie_oauth import build_authorize_url


def test_authorize_url_has_required_params():
    url = build_authorize_url("my_client", "https://localhost:8443/callback", "xyz")
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    assert parsed.netloc == "www.bungie.net"
    assert q["response_type"] == ["code"]
    assert q["client_id"] == ["my_client"]
    assert q["state"] == ["xyz"]
    assert q["redirect_uri"] == ["https://localhost:8443/callback"]
