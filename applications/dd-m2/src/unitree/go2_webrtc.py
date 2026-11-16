import asyncio

from unitree_webrtc_connect.webrtc_driver import (
    UnitreeWebRTCConnection
)


class Go2WebRTC:
    def __init__(self, **connection_options):
        self.connection_options = connection_options
        self.connection = None
        self.connected = False

    async def connect(self):
        if self.connected:
            return

        self.connection = UnitreeWebRTCConnection(
            **self.connection_options
        )

        try:
            await self.connection.connect()
        except Exception:
            self.connection = None
            self.connected = False
            raise

        self.connected = True

    async def disconnect(self):
        if self.connection is not None:
            try:
                result = self.connection.disconnect()

                if asyncio.iscoroutine(result):
                    await result
            finally:
                self.connection = None
                self.connected = False

    def status(self):
        return {
            "connected": self.connected,
            "driver": "unitree-webrtc-connect",
            "motion_enabled": False,
        }


def main():
    # Offline preparation: no robot connection.
    client = Go2WebRTC()

    print("=== GO2 WEBRTC ===")
    print("Driver:", client.status()["driver"])
    print("Connected:", client.status()["connected"])
    print("Motion enabled:", client.status()["motion_enabled"])
    print("Connection will be configured when Go2 arrives.")


if __name__ == "__main__":
    main()
