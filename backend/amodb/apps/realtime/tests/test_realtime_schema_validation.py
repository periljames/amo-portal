from amodb.apps.realtime.schemas import RealtimeEnvelope, RealtimeKind


def test_realtime_envelope_accepts_supported_kind():
    envelope = RealtimeEnvelope.model_validate(
        {
            "v": 1,
            "id": "msg-1",
            "ts": 1730000000000,
            "amoId": "amo-1",
            "userId": "user-1",
            "kind": RealtimeKind.CHAT_SEND,
            "payload": {"threadId": "thread-1", "body": "hello"},
        }
    )
    assert envelope.kind == RealtimeKind.CHAT_SEND


def test_realtime_envelope_rejects_unknown_kind():
    try:
        RealtimeEnvelope.model_validate(
            {
                "v": 1,
                "id": "msg-1",
                "ts": 1730000000000,
                "amoId": "amo-1",
                "userId": "user-1",
                "kind": "chat.nope",
                "payload": {},
            }
        )
    except Exception as exc:
        assert "kind" in str(exc)
    else:
        raise AssertionError("validation should fail")
