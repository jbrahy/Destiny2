import os
from importlib import reload

def test_settings_expose_db_and_session_fields(monkeypatch, tmp_path):
    # Temporarily replace .env with a nonexistent file to test defaults
    monkeypatch.setenv("DB_HOST", "db.example")
    monkeypatch.setenv("DB_NAME", "advisor")
    monkeypatch.setenv("TOKEN_ENC_KEY", "k")
    monkeypatch.setenv("SESSION_SECRET", "s")
    # Monkeypatch the working directory to temp dir so .env isn't found
    monkeypatch.chdir(tmp_path)
    import app.config as cfg
    reload(cfg)
    cfg.get_settings.cache_clear()
    s = cfg.get_settings()
    assert s.db_host == "db.example"
    assert s.db_name == "advisor"
    assert s.db_port == 3306
    assert s.session_ttl_days == 30
    assert s.cookie_secure is True
    assert s.bungie_throttle_concurrency == 20
    assert not hasattr(s, "db_path")
