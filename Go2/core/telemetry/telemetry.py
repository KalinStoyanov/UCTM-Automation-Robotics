import asyncio
import json

from unitree_webrtc_connect import (
    UnitreeWebRTCConnection,
    WebRTCConnectionMethod,
)
from unitree_webrtc_connect.constants import RTC_TOPIC


def on_telemetry(message):
    print(json.dumps(message, indent=2, default=str))


async def main():
    print("Unitree Go2 Air — Telemetry")
    print("Connection: LocalAP")
    print("Robot IP: 192.168.12.1")
    print("Motion commands: DISABLED")

    connection = UnitreeWebRTCConnection(
        WebRTCConnectionMethod.LocalAP,
        device_type="Go2",
    )

    try:
        print("Connecting...")
        await connection.connect()
        print("WebRTC connection: PASS")

        connection.datachannel.pub_sub.subscribe(
            RTC_TOPIC["LOW_STATE"],
            on_telemetry,
        )

        connection.datachannel.pub_sub.subscribe(
            RTC_TOPIC["SPORT_MOD_STATE"],
            on_telemetry,
        )

        print("Telemetry subscriptions registered")
        print("Press Ctrl+C to stop")

        while True:
            await asyncio.sleep(1)

    finally:
        if connection.pc is not None:
            await connection.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTelemetry stopped")
