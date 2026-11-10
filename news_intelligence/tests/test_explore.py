import explore


def test_token_lengths_without_tokenizer(monkeypatch):
    import config
    monkeypatch.setattr(config, "MODEL_NAME", "no-such-org/no-such-model")
    tokens, err = explore.token_lengths(["hello"])
    assert tokens is None and err            # offline or missing package: reported, not crashed


def test_environment_report_shape():
    rep = explore.environment_report()
    for key in ("python", "os", "cpu_threads", "packages", "ram_total_gb"):
        assert key in rep


def test_no_args_prints_help(capsys):
    assert explore.main([]) == 0
    assert "--lengths" in capsys.readouterr().out
