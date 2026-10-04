"""tests/test_logging_setup.py"""
import logging

import core.logging_setup as logging_setup


def test_configure_logging_is_idempotent(tmp_path):
    logging_setup._configured = False
    logging_setup.configure_logging(log_dir=tmp_path)
    handlers_after_first = list(logging.getLogger().handlers)

    logging_setup.configure_logging(log_dir=tmp_path)  # second call: no-op
    assert list(logging.getLogger().handlers) == handlers_after_first
    logging_setup._configured = False  # reset for other tests


def test_sensitive_data_filter_redacts_known_secret():
    f = logging_setup.SensitiveDataFilter(known_secrets=["sk-supersecret123"])
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="Using API key sk-supersecret123 to call Gemini", args=(), exc_info=None,
    )
    f.filter(record)
    assert "sk-supersecret123" not in record.getMessage()
    assert "REDACTED" in record.getMessage()


def test_sensitive_data_filter_redacts_secret_shaped_pattern():
    f = logging_setup.SensitiveDataFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg='config: {"gemini_api_key": "AIzaSyABCDEF1234567890"}', args=(), exc_info=None,
    )
    f.filter(record)
    assert "AIzaSyABCDEF1234567890" not in record.getMessage()


def test_register_secret_adds_to_global_filter():
    logging_setup.register_secret("newly-issued-secret-999")
    assert "newly-issued-secret-999" in logging_setup._sensitive_filter._known_secrets


def test_non_secret_messages_pass_through_unchanged():
    f = logging_setup.SensitiveDataFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="Dashboard listening on https://192.168.1.5:8000", args=(), exc_info=None,
    )
    f.filter(record)
    assert record.getMessage() == "Dashboard listening on https://192.168.1.5:8000"
