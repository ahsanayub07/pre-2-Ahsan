import pytest

import config


def test_missing_password_refused():
    with pytest.raises(config.ConfigError):
        config.load_db_settings({})


def test_placeholder_password_refused():
    with pytest.raises(config.ConfigError):
        config.load_db_settings({"DB_PASSWORD": "change_me"})


def test_bad_port_refused():
    with pytest.raises(config.ConfigError):
        config.load_db_settings({"DB_PASSWORD": "x", "DB_PORT": "abc"})


def test_defaults_and_no_password_in_repr():
    s = config.load_db_settings({"DB_PASSWORD": "s3cret-value"})
    assert (s.host, s.port, s.dbname, s.user) == ("localhost", 5432, "task3_articles", "task3_user")
    assert "s3cret-value" not in repr(s)


def test_classes():
    assert len(config.CLASSES) == len(set(config.CLASSES)) == 6
    assert "other" in config.CLASSES
