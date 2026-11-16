"""WebRTC adapter for Unitree Go2 Air.

Initial version: offline preparation only.
"""

from unitree_webrtc_connect.webrtc_driver import (
    UnitreeWebRTCConnection,
    WebRTCConnectionMethod,
)


ROBOT_IP = "192.168.12.1"
CONNECTION_TIMEOUT = 15.0
LIVE_ENABLED = False


class Go2WebRTC:
    def __init__(self):
        self.connection = None
        self.state = "DISCONNECTED"

    def channel_ready(self):
        """Check whether the WebRTC data channel is validated and open."""
        if self.connection is None:
            return False

        datachannel = getattr(self.connection, "datachannel", None)
        if datachannel is None:
            return False

        channel = getattr(datachannel, "channel", None)

        return (
            datachannel.data_channel_opened is True
            and channel is not None
            and channel.readyState == "open"
        )

    async def connect(self):
        if not LIVE_ENABLED:
            raise RuntimeError("LIVE WebRTC connection is disabled")

        raise NotImplementedError("Connection implementation pending")

    async def disconnect(self):
        if not LIVE_ENABLED:
            raise RuntimeError("LIVE WebRTC connection is disabled")

        raise NotImplementedError("Disconnection implementation pending")


if __name__ == "__main__":
    adapter = Go2WebRTC()
    assert adapter.state == "DISCONNECTED"
    assert adapter.channel_ready() is False
    print("Go2 WebRTC adapter: PASS")
    print("LIVE enabled:", LIVE_ENABLED)
    print("Robot IP:", ROBOT_IP)
