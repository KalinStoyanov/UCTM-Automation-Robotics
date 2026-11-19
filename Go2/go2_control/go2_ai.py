import argparse
import asyncio
import queue
import threading
import time
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mpt
from mediapipe.tasks.python import vision
from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod
from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD

ACTIONS = {"Thumb_Up": "Hello", "Closed_Fist": "Sit", "Open_Palm": "RiseSit", "Victory": "Stretch"}
STREAK = 8
COOLDOWN = 4.0


class Robot:
    def __init__(self):
        self.frames = queue.Queue(maxsize=1)
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        asyncio.run_coroutine_threadsafe(self._connect(), self.loop).result(timeout=40)

    async def _connect(self):
        self.conn = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalAP)
        await self.conn.connect()
        print("CONNECTED")
        self.conn.video.add_track_callback(self._on_track)
        res = self.conn.video.switchVideoChannel(True)
        if asyncio.iscoroutine(res):
            await res

    async def _on_track(self, track):
        while True:
            frame = await track.recv()
            img = frame.to_ndarray(format="bgr24")
            try:
                self.frames.get_nowait()
            except queue.Empty:
                pass
            self.frames.put(img)

    def send(self, name):
        async def go():
            r = await self.conn.datachannel.pub_sub.publish_request_new(RTC_TOPIC["SPORT_MOD"], {"api_id": SPORT_CMD[name]})
            return r.get("data", {}).get("header", {}).get("status", {}).get("code")
        fut = asyncio.run_coroutine_threadsafe(go(), self.loop)
        fut.add_done_callback(lambda f: print(name, "код:", f.exception() or f.result()))

    def close(self):
        try:
            asyncio.run_coroutine_threadsafe(self.conn.disconnect(), self.loop).result(timeout=5)
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--webcam", action="store_true")
    args = ap.parse_args()
    missing = [a for a in ACTIONS.values() if a not in SPORT_CMD]
    print("Липсващи команди:", missing or "няма")
    rec = vision.GestureRecognizer.create_from_options(vision.GestureRecognizerOptions(
        base_options=mpt.BaseOptions(model_asset_path="gesture_recognizer.task"),
        running_mode=vision.RunningMode.VIDEO))
    robot = None if args.webcam else Robot()
    cap = cv2.VideoCapture(0) if args.webcam else None
    last, streak, last_sent, ts = None, 0, 0.0, 0
    try:
        while True:
            if cap is not None:
                ok, frame = cap.read()
                if not ok:
                    break
            else:
                try:
                    frame = robot.frames.get(timeout=5)
                except queue.Empty:
                    print("Няма видео от робота")
                    continue
            ts += 33
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            res = rec.recognize_for_video(img, ts)
            g = res.gestures[0][0].category_name if res.gestures else "None"
            streak = streak + 1 if g == last else 1
            last = g
            action = ACTIONS.get(g)
            now = time.monotonic()
            if action and streak == STREAK and now - last_sent > COOLDOWN:
                last_sent = now
                print("Жест", g, "->", action)
                if robot:
                    robot.send(action)
            cv2.putText(frame, g + " -> " + (action or "-"), (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
            cv2.imshow("go2 ai", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        if cap is not None:
            cap.release()
        if robot:
            robot.close()
        cv2.destroyAllWindows()


main()
