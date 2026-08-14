import json

from app import config


def test_save_config_is_immediately_durable(tmp_path, monkeypatch):
    """A later save must never be overwritten by an older queued snapshot."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_FILE", config_file)
    original = config.CONFIG.daily_apply_limit
    try:
        config.CONFIG.daily_apply_limit = 139
        config.save_config()
        assert json.loads(config_file.read_text(encoding="utf-8"))["daily_apply_limit"] == 139

        config.CONFIG.daily_apply_limit = 140
        config.save_config()
        assert json.loads(config_file.read_text(encoding="utf-8"))["daily_apply_limit"] == 140
    finally:
        config.CONFIG.daily_apply_limit = original
