import asyncio
from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod
from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD

HELP = "u стани | b баланс (преди ходене) | s седни | r стани от седнало | l легни | h здрасти | w x напред назад | a d завой | q изход"
POSES = {"u": "StandUp", "b": "BalanceStand", "s": "Sit", "r": "RiseSit", "l": "StandDown", "h": "Hello"}
MOVES = {"w": (0.3, 0.0), "x": (-0.3, 0.0), "a": (0.0, 0.6), "d": (0.0, -0.6)}

async def send(conn, name, param=None, quiet=False):
    opts = {"api_id": SPORT_CMD[name]}
    if param is not None:
        opts["parameter"] = param
    r = await conn.datachannel.pub_sub.publish_request_new(RTC_TOPIC["SPORT_MOD"], opts)
    code = r.get("data", {}).get("header", {}).get("status", {}).get("code")
    if not quiet or code != 0:
        print(name, "код:", code)

async def main():
    conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
    await conn.connect()
    print("CONNECTED")
    print(HELP)
    try:
        while True:
            k = (await asyncio.to_thread(input, "> ")).strip().lower()
            if k == "q":
                break
            try:
                if k in POSES:
                    await send(conn, POSES[k])
                elif k in MOVES:
                    x, z = MOVES[k]
                    for _ in range(10):
                        await send(conn, "Move", {"x": x, "y": 0.0, "z": z}, quiet=True)
                        await asyncio.sleep(0.1)
                    await send(conn, "StopMove")
                else:
                    print(HELP)
            except Exception as e:
                print("ГРЕШКА:", e)
    finally:
        try:
            await send(conn, "StopMove")
        except Exception:
            pass
        await conn.disconnect()

asyncio.run(main())
