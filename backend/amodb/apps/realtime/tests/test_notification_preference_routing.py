from amodb.apps.realtime import notification_preferences
from amodb.apps.realtime import production_messaging
from amodb.apps.realtime import router


def test_notification_routes_use_complete_preference_service():
    assert router.messaging is production_messaging
    assert production_messaging.get_preferences is notification_preferences.get_preferences
    assert production_messaging.update_preferences is notification_preferences.update_preferences


def test_complete_preference_payload_exposes_optional_email_classes():
    class PreferenceRow:
        in_app_enabled = True
        desktop_enabled = True
        sound_enabled = True
        email_enabled = False
        receipt_email_enabled = True
        marketing_email_enabled = False
        chat_enabled = True
        quiet_hours_start = None
        quiet_hours_end = None
        timezone_name = "Africa/Nairobi"
        updated_at = None

    payload = notification_preferences.preference_payload(PreferenceRow())

    assert payload["receipt_email_enabled"] is True
    assert payload["marketing_email_enabled"] is False
    assert payload["mandatory_email_classes"] == ["ESSENTIAL", "CRITICAL"]
