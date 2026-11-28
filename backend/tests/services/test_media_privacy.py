import logging

from app.services.media_privacy import MediaTokenFilter, scrub_event


def test_media_token_is_redacted_from_access_log_args():
    record = logging.LogRecord(
        "uvicorn.access",
        20,
        "",
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("loopback", "GET", "/api/v1/app/media/read?token=secret.jwt&x=1", "1.1", 200),
        None,
    )
    assert MediaTokenFilter().filter(record)
    assert "secret.jwt" not in record.getMessage()
    assert "token=[REDACTED]&x=1" in record.getMessage()


def test_media_token_is_redacted_from_nested_error_and_trace_data():
    event = {
        "request": {
            "url": "https://api.example.com/app/media/read?token=secret",
            "query_string": "token=secret&safe=1",
        },
        "breadcrumbs": [{"data": {"token": "secret"}}],
    }
    result = scrub_event(event, {})
    assert "secret" not in repr(result)
    assert result["request"]["query_string"] == "token=[REDACTED]&safe=1"
    assert event["request"]["query_string"] == "token=secret&safe=1"


def test_percent_encoded_query_key_is_also_redacted():
    event = {"request": {"query_string": "%74%6f%6b%65%6e=secret.jwt&x=1"}}
    assert "secret.jwt" not in repr(scrub_event(event, {}))
