"""Read-only telemetry receiver for Unitree Go2 Air."""

from datetime import datetime, timezone
from unitree_webrtc_connect.constants import RTC_TOPIC


TELEMETRY_TOPICS = {
    name: RTC_TOPIC[name]
    for name in (
        "SPORT_MOD_STATE",
        "LOW_STATE",
        "BMS_STATE",
        "MAIN_BOARD_STATE",
        "LF_SPORT_MOD_STATE",
    )
}


class Go2Telemetry:
    def __init__(self):
        self.messages = {}
        self.timestamps = {}
        self.counts = {}

    def on_message(self, message):
        if not isinstance(message, dict):
            return

        topic = message.get("topic")

        if topic not in TELEMETRY_TOPICS.values():
            return

        self.messages[topic] = message
        self.timestamps[topic] = datetime.now(timezone.utc)
        self.counts[topic] = self.counts.get(topic, 0) + 1

    def subscribe(self, connection):
        for topic in TELEMETRY_TOPICS.values():
            connection.datachannel.pub_sub.subscribe(
                topic, self.on_message
            )

    def unsubscribe(self, connection):
        for topic in TELEMETRY_TOPICS.values():
            connection.datachannel.pub_sub.unsubscribe(topic)


if __name__ == "__main__":
    receiver = Go2Telemetry()

    test_topic = TELEMETRY_TOPICS["SPORT_MOD_STATE"]

    receiver.on_message({
        "topic": test_topic,
        "data": {"test": True}
    })

    assert receiver.counts[test_topic] == 1
    assert receiver.messages[test_topic]["data"]["test"] is True

    print("M24-A.11: PASS")
    print("Telemetry topics:", len(TELEMETRY_TOPICS))
    print("Received messages:", receiver.counts)
