"""WebRTC adapter for Unitree Go2 Air.

Initial version: offline preparation only.
"""

import asyncio
from go2_transport import make_move, make_stop

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

        if self.state != "DISCONNECTED":
            raise RuntimeError("Invalid state for connect")

        self.state = "CONNECTING"

        try:
            self.connection = UnitreeWebRTCConnection(
                WebRTCConnectionMethod.LocalAP
            )

            await asyncio.wait_for(
                self.connection.connect(),
                timeout=CONNECTION_TIMEOUT + 5.0,
            )

            if not self.channel_ready():
                raise RuntimeError(
                    "WebRTC DataChannel is not ready"
                )

            self.state = "CONNECTED"
            return True

        except BaseException:
            self.state = "ERROR"

            if self.connection is not None:
                try:
                    await self.connection.disconnect()
                except Exception:
                    pass

            self.connection = None
            raise

    async def send_request(self, request):
        if not LIVE_ENABLED:
            raise RuntimeError("LIVE WebRTC connection is disabled")

        if self.state != "CONNECTED":
            raise RuntimeError("WebRTC transport is not connected")

        if not self.channel_ready():
            self.state = "ERROR"
            raise RuntimeError("WebRTC DataChannel is not ready")

        try:
            return await asyncio.wait_for(
                self.connection.datachannel.pub_sub.publish_request_new(
                    request["topic"],
                    request["options"],
                ),
                timeout=2.0,
            )
        except (
            asyncio.TimeoutError,
            asyncio.CancelledError,
            ConnectionError,
        ):
            self.state = "ERROR"
            raise

    async def send_move(self, vx=0.0, vy=0.0, wz=0.0):
        request = make_move(vx, vy, wz)
        return await self.send_request(request)

    async def stop(self):
        request = make_stop()
        return await self.send_request(request)

    async def disconnect(self):
        if self.connection is None:
            self.state = "DISCONNECTED"
            return

        self.state = "DISCONNECTING"
        connection = self.connection

        try:
            await asyncio.wait_for(
                connection.disconnect(),
                timeout=5.0,
            )
        except BaseException:
            self.state = "ERROR"
            raise
        else:
            self.connection = None
            self.state = "DISCONNECTED"


if __name__ == "__main__":
    adapter = Go2WebRTC()
    assert adapter.state == "DISCONNECTED"
    assert adapter.channel_ready() is False
    print("Go2 WebRTC adapter: PASS")
    print("LIVE enabled:", LIVE_ENABLED)
    print("Robot IP:", ROBOT_IP)
