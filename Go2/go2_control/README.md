# Go2 Control

A local web controller for the Unitree Go2 Air (firmware 1.1.12, AP mode, 192.168.12.1) with live video, joysticks and keyboard driving, safe actions, telemetry and AI modes. It replaces the phone app for the demo.

The robot accepts **one** WebRTC client. Video, telemetry and commands therefore share a single connection inside one process (`controller/robot.py`). **Close the Unitree app on every phone before you start.**

## Run

```bash
cd Go2/go2_control

# One-time setup (Python 3.12, macOS arm64; needs internet once)
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-go2-control.txt

# Or double-click start.command (opens the browser; passes flags through, e.g. --sim)

# Robot (Mac on the robot's WiFi)
.venv/bin/python -m controller.app

# Simulation (no robot): Mac webcam as video, commands only logged
.venv/bin/python -m controller.app --sim
.venv/bin/python -m controller.app --sim --camera 1                         # specific webcam
.venv/bin/python -m controller.app --sim --camera path/to/image_or_video   # image/video file instead of a webcam

# Unit tests (deadman, caps, BalanceStand, 10 Hz with a silent robot, whitelist, follow math/tracking/override)
.venv/bin/python -m unittest discover -s controller/tests -t . -v
```

Open **http://localhost:8080**. A tablet on the same WiFi can use `http://<Mac IP>:8080`.
Stop with Ctrl+C. Shutdown sends StopMove before it disconnects.

Other flags: `--port 8080`, `--host 0.0.0.0`, `--no-connect` (start without connecting; use the "Свържи" button).
If the connection drops, the app retries every ~3 s. That also covers "the phone app was still connected".

Logs go to the terminal and to `logs/controller-YYYYMMDD.log`.
- Actions, StopMove and BalanceStand are awaited (reply timeout 1 s) and logged with their code: `CMD Hello -> code=0 (12 ms)`.
- **Move is fire-and-forget** (`pub_sub.publish_without_callback`), so the 10 Hz loop never waits on the robot. It is logged once at start and then at most once per second, with the last reply code if the robot sends one: `CMD Move x=+0.30 y=+0.00 z=+0.60 -> 10 sent in 1.0 s, last reply code=0`.

## Controls

| Input | Effect |
|---|---|
| W / S or ↑ / ↓ | forward / back |
| A / D | strafe left / right |
| Q / E or ← / → | turn left / right |
| **Space** or red **СТОП** | StopMove (also releases all keys and joysticks) |
| 1 … 9, 0 | the first ten buttons: Поза (Стани, Легни, Баланс, Възстанови, Седни, Изправи от седнало), then Здрасти, Протягане, Танц 1, Танц 2 |
| Трикове | Здрасти, Протягане, Танц 1, Танц 2, Радост (Content), Поклон (Scrape), Сърце (FingerHeart). They stand the robot up automatically when needed. Only commands the firmware accepts are offered (api id in the library's `SPORT_CMD_MCF`); Кълчене (WiggleHips) answered code 3203 on firmware 1.1.12 and is hidden. |
| Left joystick | move (forward/back + strafe) |
| Right joystick | turn |
| Бавно / Нормално / Бърз | 0.3 m/s · 0.6 rad/s / 0.6 · 1.0 / 1.0 · 1.5 (`SPEED_PRESETS` in robot.py). **Бавно on every page load.** |
| ? (or the keyboard icon) | key legend on/off (Esc closes) |
| Демо | Здрасти → Протягане → Седни → Изправи от седнало (see below) |
| Още (collapsed) | body tilt (Euler pitch/roll ±0.15 rad) and Нулирай позата. A tilt first switches on **pose mode** (`Pose`, 1028): on fw 1.1.12 Euler answered code 0 but did not move in the normal balance stand. Any other command or movement turns pose mode off first. Height (BodyHeight) is hidden: the firmware answers code 3203. |

Keys use physical positions (`KeyboardEvent.code`), so they also work with the Bulgarian layout. Key-up, window blur and a hidden tab all send zero velocity. When a slider has focus, the arrow keys adjust the slider instead of driving.

**Демо** (`controller/demo.py`, steps and pauses at the top of the file): each step starts only after the previous command replied (or timed out after 1 s), plus a pause for the motion (4 / 5 / 3 / 3 s). It never sends Move. The current step shows on the button and in the step strip. **СТОП, Space, any key or joystick, an action, a posture slider or "Спри демото"** cancels it immediately. Starting the demo turns follow mode off.

**AI modes are all off on every page load** and must be turned on by hand.

## Automatic posture transitions

The controller keeps an **inferred posture** (Стои / Седи / Лежи, shown as "Поза" in the top bar). It is updated from the commands we send. It is also updated from `rt/lf/sportmodestate` when the mode clearly confirms it: 1 or 3 = standing, 5 = lying, 10 = sitting. Telemetry is ignored while a chain runs and for 2 s after a posture command. Before an action, the missing steps are inserted automatically, and each step waits for its motion time from `controller/timing.py` (the same table the demo uses):

| Action | Needs | Inserted when lying / sitting |
|---|---|---|
| Здрасти, Протягане, tricks, Седни, Наклон, Височина, any movement | standing (balanced) | Стани → Баланс / Изправи от седнало → Баланс |
| Легни | not sitting | Изправи от седнало first |
| Стани / Изправи от седнало | | skipped when already standing; from sitting Стани becomes Изправи от седнало and vice versa |

- Movement keeps the BalanceStand rule: after Стани, Moves start only after BalanceStand. While a chain runs, Moves are held, and the top-bar posture pulses.
- Inserted steps never wait on their reply, so an unanswered step can't stall anything. A step the robot **refuses** (non-zero code) aborts the chain and the posture is not changed.
- **СТОП cancels a pending chain.** A new action replaces a chain that is still preparing.
- Every auto step shows in the log: e.g. `Авто: Стани → Баланс преди Здрасти`.
- Until telemetry or a command decides, the posture is `—` (unknown), which is treated like lying: Стани → Баланс first.

## Safety model

- **СТОП during a trick:** the robot answers nothing while a trick runs. On 19 Nov, StopMove during Dance2 got no reply for 12 s; Dance1 replied only when it ended, after 16 s; the robot reports FSM 1006 meanwhile. So СТОП during a trick sends StopMove **and then BalanceStand**, logs both replies, logs late replies when the trick ends, and logs the robot's FSM state 2 s later.
- **Аварийно · Damp** (below СТОП): **press and hold 1.5 s**. The motors go limp and the robot lowers itself to the ground. It cancels the demo, follow and chains; the server refuses holds shorter than 1.4 s. Damp is still not an ordinary action.
- **Танц 1 / Танц 2** ask first: "Нужни са 2 m свободно място наоколо".

- The server caps every velocity: |vx|, |vy| ≤ 1.0 m/s and |vyaw| ≤ 1.5 rad/s. Whatever the UI sends, NaN and garbage become 0.
- `Move` is sent at 10 Hz only while the velocity is non-zero. A zero velocity sends StopMove once.
- **Deadman**: if there is no velocity update for 300 ms, StopMove is sent once (for example a tab crash or a WiFi drop). The client stops on key-up, on window blur and when the tab is hidden. If the driving browser disconnects, the robot stops.
- After **StandUp** or **RiseSit**, BalanceStand is sent automatically before the first Move.
- An action that arrives while the robot is moving sends StopMove first.
- Server-side whitelist: flips, jumps, pounce, handstand, bound, moonwalk, stand-on-hind-legs (StandOut), Wallow and **Damp** are rejected even when sent by hand. Wallow and Trigger are also left out of the UI (Wallow rolls the robot onto its back; Trigger is a reserved id with unclear meaning). Dance3/Dance4 are not in this library's `SPORT_CMD`. Actions appear only if their name exists in the installed `SPORT_CMD`.

## AI modes

- **Жестове** (MediaPipe, `gesture_recognizer.task`), from the single `MAPPING` table at the top of `controller/ai/gestures.py`: Thumb_Up → Здрасти, Closed_Fist → Седни, Open_Palm → Изправи от седнало, Victory → Сърце (FingerHeart), Pointing_Up → Стани, Thumb_Down → Легни. Протягане is a button only; ILoveYou is not mapped (it was not recognised reliably on the robot). Every gesture action goes through the posture logic (e.g. Стани from sitting = Изправи от седнало). Юмрук or Палец надолу while following also turns follow off, so the robot doesn't stand up again and walk away. A gesture fires after 8 consecutive frames plus a 4 s cooldown, and fires once per hold. Lower the hand and show the gesture again to repeat it. Hand landmarks and the label are drawn on the video. The recognizer runs in its own thread on the newest frame and never blocks robot control.
- **Обекти** (YOLO11n, `models/yolo11n.pt`): object boxes and counts. Overlay only, no robot actions. `YOLO_OFFLINE=1` stops it from going online.
- **Следване** (`controller/ai/follow.py`): **turning it on only arms it; the robot does not move.** The overlay and the AI panel show "Вдигни ръка, за да те следвам".
  - **Start:** a person holds **one arm above the head for ~1 s**, and follow locks onto that person ("Следвам"). It is an upper layer that only calls `set_velocity` / `stop`, just like the keyboard, so the caps, the deadman and the posture logic still apply.
  - **Stop following** ("Спрях", then armed again after 2 s): the target holds **both arms above the head for ~1 s**, shows an **open palm** (needs Жестове on), or is **lost for 2 s**. If the target isn't seen for 0.4 s, the robot stands still rather than driving blind. СТОП, keys, joystick or an action button turn the whole mode off.
  - **Pose:** YOLO11n-pose (`models/yolo11n-pose.pt`) runs only on the YOLO person boxes (the 4 largest), at about 6–30 ms per frame on this Mac. MediaPipe pose-lite was benchmarked and was slower. "Above the head" means the wrist is above the top of the head; a hand beside the head does not count.
  - While following, someone else raising an arm is ignored; the target is kept by box overlap.
  - Control at 10 Hz: `vyaw = -K_yaw·(cx−0.5)`, clamped to ±0.6, with a ±0.05 deadzone. `vx = K_x·(TARGET_H − h)` with TARGET_H 0.75 and K_x 2.5, clamped to 0…0.6 (never backwards). Whenever it moves forward it uses at least 0.25 m/s, because slower makes the robot shuffle without stepping. There is no forward motion within 0.03 of the target height.
  - **Too close** (vx = 0): box height > 0.92, or the box touches both the top and the bottom edge of the frame. These defaults are tuned for the low robot camera.
  - K_x 2.5 assumes a person at ~3 m gives a box of ~0.5 (estimate), which means ~max speed. Check it on the robot and correct it with the slider.
  - If YOLO drops below 5 FPS, a warning appears and vx is capped at the 0.25 minimum.
  - Tunables live in the block at the top of `follow.py`. They are also sliders under "Настройки" (live, not saved).
  - **Any manual input turns it off**: W/A/S/D/Q/E, a joystick, СТОП/Space or an action button. **Open_Palm** while following stops following instead of RiseSit, with no cooldown. Follow also turns off when the last browser closes.
  - Overlay: the target is highlighted, other people are dimmed, an arrow shows the vx/ω command, plus status and AI FPS. The panel shows Целта е заключена / Търся човек… / Твърде близо.
  - After a gesture action (e.g. Здрасти) follow pauses for 4 s so the action can finish.
  - YOLO runs once for both Обекти and Следване (`ai/detector.py`).

## Files

```
controller/
  robot.py          RobotSession (WebRTC) and SimRobot: one asyncio loop thread, thread-safe API
  app.py            Flask + Flask-SocketIO (threading): /, /video (MJPEG), /snapshot.jpg, /api/telemetry
  ai/gestures.py    gesture mode
  ai/objects.py     object mode
  ai/detector.py    shared YOLO11n thread
  ai/follow.py      follow mode (tunables at the top)
  demo.py           "Демо" sequence
  timing.py         motion times per command (demo pauses, posture-chain waits, trick note)
  events.py         operator log ("Дневник") pushed to the UI
  static/           index.html, app.css, app.js; vendor/socket.io.min.js 4.8.1; fonts/ (Manrope, JetBrains Mono)
  tests/            unit tests (python -m unittest discover -s controller/tests -t .)
models/yolo11n.pt   YOLO11n weights (objects + follow); models/yolo11n-pose.pt: arm gestures for follow
gesture_recognizer.task   MediaPipe hand gestures
go2.py, go2_ai.py   original standalone scripts (CLI control, gesture demo)
requirements-go2-control.txt   pinned direct dependencies
start.command       macOS launcher
```

The frontend is fully vendored: no CDNs, no internet needed. `go2.py` and `go2_ai.py` are unchanged.

## Morning checklist (real robot)

Do these steps in order, with the robot on the floor, 2 m of free space around it, and one person standing next to it.

1. [ ] Close the Unitree app on **all** phones (swipe it away). Power on the robot and wait until it stands or lies still.
2. [ ] Connect the Mac to the robot's WiFi. Check with `ping 192.168.12.1`.
3. [ ] Start: `.venv/bin/python -m controller.app` and open http://localhost:8080.
4. [ ] The top bar shows **Свързан** (green), with no "СИМУЛАЦИЯ" tag.
   - "Роботът е зает" → a phone is still connected. Close it; the app reconnects by itself.
5. [ ] Video plays and FPS is above 0 (expect ~15–30).
6. [ ] **Battery %** shows a number that matches the robot. If it shows "—", the `rt/lf/lowstate` → `bms_state.soc` field differs: check the log.
7. [ ] **Режим** changes when the robot changes posture. If it shows "Режим N", note N. The labels come from SDK docs and are unverified on 1.1.12.
8. [ ] Press **Стани (1)** and check that the log shows `CMD StandUp -> code=0`.
9. [ ] Speed **Бавно**. Tap **W** for ~1 s. The log must show `BalanceStand` **before** the first `Move`. The robot walks forward and stops when you release W (`StopMove`).
10. [ ] Directions: **A** = robot's left, **D** = right, **Q** = turns left (counter-clockwise), **E** = right. Do the same with both joysticks.
11. [ ] Hold W and press **Space**: the robot stops immediately. Repeat with the red СТОП button.
11b. [ ] **СТОП during a trick**: start Танц 1 (confirm the dialog), press СТОП after ~3 s. Read the log: what StopMove and Баланс returned, and the line "2 s след СТОП: робот FSM …" (1006 = the trick still runs). Write down whether the robot actually stopped.
11c. [ ] **Аварийно**: with the robot standing, on a soft surface, hold "Аварийно · Damp" for 1.5 s and check that it lowers itself. Then check whether it also works **during a dance**. If the robot ignores it there too, nothing on the API can interrupt a trick; use the physical remote's emergency stop.
12. [ ] **Deadman**: hold W, then close the browser tab (Cmd+W). The robot must stop within ~0.3 s (`StopMove` in the log).
13. [ ] Awaited commands (StandUp, StopMove, BalanceStand, …) log `code=0`. If you see `timeout` (no reply within 1 s), the command was still sent; check what the robot did.
14. [ ] Try each action once and check the code is 0: Легни, Стани, Седни, Изправи от седнало (then W → expect BalanceStand), Здрасти, Протягане, Баланс, Възстанови. Run Танц 1 / Танц 2 only with plenty of room.
15. [ ] Turn on **Жестове**. Stand 1–2 m in front of the robot camera and show thumbs-up for ~1 s → Здрасти. Then try Сочи нагоре (Стани), Палец надолу (Легни) and Победа (Сърце). Check the lighting. Turn it off again.
16. [ ] Turn on **Обекти** and confirm the boxes appear and video FPS stays acceptable.
17. [ ] **Move replies**: while driving, the log line `CMD Move … last reply code=0` means the robot answers Move. `no reply` is fine too, because driving does not depend on replies, but note which one you see.
18. [ ] **Следване** (2+ m clear, the person ready to show a palm). Speed starts low (vx ≤ 0.3).
   - Turn it on: the robot must **not move** ("Вдигни ръка, за да те следвам"). Raise one arm straight up for ~1 s: "Следвам", and the robot turns toward you and walks.
   - Both arms up for ~1 s: "Спрях". Walk out of view: "Спрях (изгубих те)" after 2 s. In both cases it re-arms.
   - Step left: it turns left. Walk closer: it stops around box height 0.45. Very close: "Твърде близо", no forward motion.

   - Press W (or Space): follow turns off with the toast "ръчно управление".
   - Turn on Жестове plus Следване and show Open_Palm: follow stops (not RiseSit).
   - Check "AI N fps" ≥ 5. If it is lower, the amber warning appears and the speed is capped at 0.25.
   - Stand ~3 m away and note the box height shown in the log (`FOLLOW locked cx=… h=…`). If h at 3 m is far from 0.5, adjust K_x so (0.75 − h)·K_x ≈ 0.6. Check that it stops at a comfortable distance (TARGET_H 0.75).
   - Tune K_yaw first if it oscillates left and right, then K_x / Целева височина for the follow distance.
19. [ ] **Демо** (room around the robot, standing): press Демо and watch every step run with code 0. Press Демо again, then press Space during Протягане: nothing more may be sent. Tune the pauses in `controller/demo.py` if a step gets cut off or waits too long.
20. [ ] **Трикове** (plenty of room): run each new trick once (Радост, Поклон, Кълчене, Сърце) and note the reply code. Time how long each one takes and put the times into `controller/timing.py` (the "още върви" note on СТОП and the demo/posture waits use them).
20b. [ ] **Още**: move "Наклон напред/назад" to the end of its range while standing. The log must show `Режим поза: OK`, then `Наклон: OK`, **and the body must visibly tilt**. Then Нулирай позата, then W (walking must work again after pose mode). If it still does not tilt, hide the panel (pose mode is not the missing switch).
21. [ ] **Posture logic**: after connecting, "Поза" should switch from "—" to "Стои/Лежи/Седи" (log: `Поза от телеметрията: …`). If it stays "—", telemetry does not confirm the mode: note the mode number in the top bar. Then:
   - Легни → Здрасти: expect `Авто: Стани → Баланс преди Здрасти` and a clean stand-up before the wave.
   - Седни → W: Изправи от седнало → Баланс, then walking.
   - Седни → Легни: Изправи от седнало, then Легни.
   - During an auto chain press СТОП: the remaining steps must not be sent.
   - If a step starts before the previous motion ends (or waits too long), tune `controller/timing.py`.
22. [ ] Restart test: Ctrl+C the server (the robot must stop), start again, reload the page, and confirm it reconnects.
23. [ ] Optional: a tablet on the robot WiFi → `http://<Mac IP>:8080` (`ipconfig getifaddr en0`).

### Troubleshooting

- **"Роботът не е достъпен на 192.168.12.1"**: the Mac is not on the robot WiFi.
- **"Фърмуерът иска AES ключ"**: only firmware ≥ 1.1.15. Do **not** update the robot before the demo.
- **Video black or 0 FPS but connected**: restart the app. Only one process can hold the robot connection, so make sure `go2.py` or `go2_ai.py` is not running.
- **Robot doesn't walk after Стани**: press **Баланс (3)**, then try again.
