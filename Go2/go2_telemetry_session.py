"""Read-only telemetry session for Unitree Go2 Air."""

from go2_webrtc import Go2WebRTC
from go2_telemetry import Go2Telemetry, TELEMETRY_TOPICS


class Go2TelemetrySession:
    def __init__(self):
        self.adapter = Go2WebRTC()
        self.receiver = Go2Telemetry()
        self.subscribed = False

    async def connect(self):
        await self.adapter.connect()

        try:
            if not self.adapter.channel_ready():
                raise RuntimeError("DataChannel is not ready")

            self.receiver.subscribe(self.adapter.connection)
            self.subscribed = True
        except BaseException:
            await self.adapter.disconnect()
            raise

    async def disconnect(self):
        try:
            if self.subscribed and self.adapter.channel_ready():
                self.receiver.unsubscribe(self.adapter.connection)
        finally:
            self.subscribed = False
            await self.adapter.disconnect()

    def snapshot(self):
        return {
            "state": self.adapter.state,
            "subscribed": self.subscribed,
            "counts": dict(self.receiver.counts),
            "topics": dict(TELEMETRY_TOPICS),
        }
