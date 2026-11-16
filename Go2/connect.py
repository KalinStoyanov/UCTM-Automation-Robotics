from unitree_webrtc_connect import (
    UnitreeWebRTCConnection,
    WebRTCConnectionMethod,
)

def main():
    print("Unitree Go2 Air — connection diagnostics")
    print("Mode: LocalAP")
    print("Device: Go2")

    connection = UnitreeWebRTCConnection(
        WebRTCConnectionMethod.LocalAP,
        device_type="Go2",
    )

    print("Connection object: PASS")
    print("WebRTC session: NOT STARTED")
    print("Motion commands: DISABLED")

if __name__ == "__main__":
    main()
