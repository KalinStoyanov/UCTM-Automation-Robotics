/* Go2 Control — client. Velocity is streamed at 10 Hz while any input is active;
   the server stops the robot by itself if updates stop for 300 ms. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const app = $("app");
  // websocket only: no polling->websocket upgrade window in which velocity packets get dropped
  const socket = io({ transports: ["websocket"] });

  const GESTURE_BG = {
    Thumb_Up: "Палец нагоре", Closed_Fist: "Юмрук", Open_Palm: "Отворена длан", Victory: "Победа",
    Pointing_Up: "Сочи нагоре", Thumb_Down: "Палец надолу", ILoveYou: "Обичам те",
  };
  const DIGITS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"];

  let config = null;
  let actionLabels = {};
  // replaced by the server's presets on connect; same values as fallback
  let speeds = [{ lin: 0.3, yaw: 0.6 }, { lin: 0.6, yaw: 1.0 }, { lin: 1.0, yaw: 1.5 }];
  let speedLevel = 0;
  let linkState = "disconnected";
  let socketUp = false;

  /* ---------------- toasts ---------------- */
  function toast(text) {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = text;
    $("toasts").appendChild(el);
    setTimeout(() => { el.dataset.leaving = "true"; setTimeout(() => el.remove(), 220); }, 2600);
  }

  function flash(el) {
    el.dataset.flash = "true";
    clearTimeout(el._flashT);
    el._flashT = setTimeout(() => { el.dataset.flash = "false"; }, 450);
  }

  /* ---------------- joysticks ---------------- */
  function Stick(el, axes) {
    const base = el.querySelector(".stick-base");
    const knob = el.querySelector(".stick-knob");
    const line = el.querySelector(".stick-vec line");
    const s = { x: 0, y: 0, active: false, pointer: null };
    const DEAD = 0.08;

    function render(nx, ny, on) {
      const r = base.getBoundingClientRect();
      const maxX = (r.width - knob.offsetWidth) / 2;
      const maxY = axes === "xy" ? (r.height - knob.offsetHeight) / 2 : 0;
      knob.style.transform = `translate(${nx * maxX}px, ${ny * maxY}px)`;
      line.setAttribute("x2", ((nx * maxX) / (r.width / 2)) * 100);
      line.setAttribute("y2", ((ny * maxY) / (r.height / 2)) * 100);
      el.dataset.active = on ? "true" : "false";
    }

    function update(e) {
      const r = base.getBoundingClientRect();
      const maxX = (r.width - knob.offsetWidth) / 2 || 1;
      const maxY = (r.height - knob.offsetHeight) / 2 || 1;
      let nx = (e.clientX - (r.left + r.width / 2)) / maxX;
      let ny = axes === "xy" ? (e.clientY - (r.top + r.height / 2)) / maxY : 0;
      const m = Math.hypot(nx, ny);
      if (m > 1) { nx /= m; ny /= m; }
      const mag = Math.min(1, m);
      // dead zone with rescale so small wobbles never move the robot
      const k = mag < DEAD ? 0 : (mag - DEAD) / (1 - DEAD) / (mag || 1);
      s.x = nx * k;
      s.y = -ny * k; // up = positive
      render(nx, ny, true);
      onInput();
    }

    function release() {
      if (s.pointer === null && !s.active) return;
      s.pointer = null; s.active = false; s.x = 0; s.y = 0;
      render(0, 0, false);
      onInput();
    }

    base.addEventListener("pointerdown", (e) => {
      if (s.pointer !== null) return; // ignore extra fingers
      e.preventDefault();
      s.pointer = e.pointerId; s.active = true;
      base.setPointerCapture(e.pointerId);
      update(e);
    });
    base.addEventListener("pointermove", (e) => { if (e.pointerId === s.pointer) update(e); });
    for (const t of ["pointerup", "pointercancel", "lostpointercapture"]) {
      base.addEventListener(t, (e) => { if (e.pointerId === s.pointer) release(); });
    }
    el.addEventListener("contextmenu", (e) => e.preventDefault());

    s.release = release;
    s.show = (nx, ny, on) => { if (!s.active) render(nx, ny, on); };
    return s;
  }

  const moveStick = Stick($("stickMove"), "xy");
  const turnStick = Stick($("stickTurn"), "x");

  /* ---------------- keyboard ---------------- */
  const keys = new Set();
  const DRIVE = new Set(["KeyW", "KeyS", "KeyA", "KeyD", "KeyQ", "KeyE", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]);
  // a focused slider keeps its arrow keys (adjusting it must not drive the robot)
  const ownsArrows = (el) => el && el.tagName === "INPUT" && el.type === "range";

  window.addEventListener("keydown", (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.code === "Space" || e.key === "Escape") {
      e.preventDefault();
      if (e.key === "Escape") toggleLegend(false);
      if (!e.repeat) emergencyStop();
      return;
    }
    if (e.key === "?") { e.preventDefault(); toggleLegend(); return; }
    if (e.code.startsWith("Arrow") && ownsArrows(e.target)) return;
    if (DRIVE.has(e.code)) {
      e.preventDefault();
      // Only a fresh press drives. Auto-repeat of a key that is still held after СТОП
      // must not re-arm motion (that made СТОП look like it did nothing while W was held).
      if (!e.repeat && !keys.has(e.code)) { keys.add(e.code); onInput(); }
      return;
    }
    const d = e.code.startsWith("Digit") ? e.code.slice(5) : null;
    if (d !== null && !e.repeat && config) {
      const a = config.actions[DIGITS.indexOf(d)];
      if (a) { e.preventDefault(); runAction(a.name); }
    }
  });
  window.addEventListener("keyup", (e) => {
    if (e.code === "Space") { e.preventDefault(); return; }
    if (keys.delete(e.code)) onInput();
  });

  function releaseAll() {
    keys.clear();
    moveStick.release();
    turnStick.release();
    onInput();
  }
  window.addEventListener("blur", releaseAll);
  document.addEventListener("visibilitychange", () => { if (document.hidden) releaseAll(); });

  /* ---------------- velocity stream ---------------- */
  const clamp1 = (v) => Math.max(-1, Math.min(1, v));
  const k = (c) => (keys.has(c) ? 1 : 0);
  let streaming = false;
  let lastVel = { vx: 0, vy: 0, vyaw: 0 };

  function computeVel() {
    const sp = speeds[speedLevel];
    const kf = Math.max(k("KeyW"), k("ArrowUp")) - Math.max(k("KeyS"), k("ArrowDown"));
    const ks = k("KeyA") - k("KeyD");
    const kt = Math.max(k("KeyQ"), k("ArrowLeft")) - Math.max(k("KeyE"), k("ArrowRight"));
    const fwd = clamp1(moveStick.y + kf);
    const side = clamp1(-moveStick.x + ks);
    const turn = clamp1(-turnStick.x + kt);
    // keyboard input drives the same instruments as touch
    moveStick.show(-ks / (ks && kf ? Math.SQRT2 : 1), -kf / (ks && kf ? Math.SQRT2 : 1), !!(kf || ks));
    turnStick.show(-kt, 0, !!kt);
    const r = (v) => Math.round(v * 1000) / 1000;
    return { vx: r(fwd * sp.lin), vy: r(side * sp.lin), vyaw: r(turn * sp.yaw) };
  }

  function renderVel(v) {
    const f = (x) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2);
    for (const key of ["vx", "vy", "vyaw"]) {
      const el = $(key);
      el.textContent = f(v[key]);
      el.parentElement.dataset.active = v[key] !== 0 ? "true" : "false";
    }
  }

  function pump() {
    const v = computeVel();
    const moving = v.vx !== 0 || v.vy !== 0 || v.vyaw !== 0;
    if (moving) {
      socket.volatile.emit("velocity", v);
      streaming = true;
    } else if (streaming) {
      socket.emit("velocity", { vx: 0, vy: 0, vyaw: 0 });
      streaming = false;
    }
    if (v.vx !== lastVel.vx || v.vy !== lastVel.vy || v.vyaw !== lastVel.vyaw) renderVel(v);
    lastVel = v;
  }
  let lastInputPump = 0;
  function onInput() {
    // immediate response on press/release, but never faster than ~20 Hz from pointer moves
    const now = performance.now();
    if (now - lastInputPump > 50 || (lastVel.vx === 0 && lastVel.vy === 0 && lastVel.vyaw === 0)) {
      lastInputPump = now;
      pump();
    } else {
      const v = computeVel();
      if (v.vx === 0 && v.vy === 0 && v.vyaw === 0) pump();
    }
  }
  setInterval(pump, 100);

  function emergencyStop() {
    keys.clear();
    moveStick.release();
    turnStick.release();
    streaming = false;
    lastVel = { vx: 0, vy: 0, vyaw: 0 };
    renderVel(lastVel);
    socket.emit("stop");
    const btn = $("stopBtn");
    flash(btn);
    $("stopLabel").textContent = "СПРЯНО";
    clearTimeout(btn._labelT);
    btn._labelT = setTimeout(() => { $("stopLabel").textContent = "СТОП"; }, 900);
    if (!socketUp) addFeed({ t: Date.now() / 1000, text: "СТОП: няма връзка със сървъра!", level: "danger" });
  }

  /* ---------------- operator log ("Дневник") ---------------- */
  const FEED_MAX = 6;
  const seenIds = new Set();
  function addFeed(e) {
    if (e.id && seenIds.has(e.id)) return;
    if (e.id) seenIds.add(e.id);
    const ol = $("feed");
    const li = document.createElement("li");
    li.dataset.level = e.level || "info";
    const d = new Date(e.t * 1000);
    const time = document.createElement("time");
    const pad = (n) => String(n).padStart(2, "0");
    time.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    const span = document.createElement("span");
    span.textContent = e.text;
    li.append(time, span);
    ol.appendChild(li);
    while (ol.children.length > FEED_MAX) ol.firstElementChild.remove();
  }
  // Stop on pointerdown (no waiting for release); click covers Enter and assistive tech.
  let stopDownAt = 0;
  $("stopBtn").addEventListener("pointerdown", (e) => { e.preventDefault(); stopDownAt = performance.now(); emergencyStop(); });
  $("stopBtn").addEventListener("click", () => { if (performance.now() - stopDownAt > 600) emergencyStop(); });

  /* ---------------- speed ---------------- */
  const segButtons = [...$("speedSeg").querySelectorAll("button")];
  function setSpeed(i) {
    speedLevel = i;
    segButtons.forEach((b, j) => b.setAttribute("aria-checked", String(j === i)));
  }
  segButtons.forEach((b, i) => b.addEventListener("click", () => setSpeed(i)));
  setSpeed(0); // Бавно on every page load (deliberately not remembered)

  /* ---------------- key legend ---------------- */
  function toggleLegend(force) {
    const el = $("keyLegend");
    const show = typeof force === "boolean" ? force : el.hidden;
    el.hidden = !show;
    $("legendBtn").setAttribute("aria-expanded", String(show));
  }
  $("legendBtn").addEventListener("click", () => toggleLegend());

  /* ---------------- demo ---------------- */
  function renderDemoSteps() {
    const ol = $("demoSteps");
    ol.textContent = "";
    for (const n of config.demo_steps || []) {
      const li = document.createElement("li");
      li.textContent = actionLabels[n] || n;
      ol.appendChild(li);
    }
    $("demo").hidden = !(config.demo_steps || []).length;
  }

  function renderDemo(d) {
    if (!d) return;
    const box = $("demo");
    box.dataset.running = String(d.running);
    $("demoBtnText").textContent = d.running
      ? `Спри демото · ${Math.max(1, d.step + 1)}/${d.steps.length} ${actionLabels[d.steps[d.step]] || ""}`.trim()
      : "Демо";
    [...$("demoSteps").children].forEach((li, i) => {
      li.dataset.state = !d.running ? "" : i < d.step ? "done" : i === d.step ? d.phase : "";
    });
  }

  $("demoBtn").addEventListener("click", () => {
    const running = $("demo").dataset.running === "true";
    if (!running && linkState !== "connected") { toast("Роботът не е свързан"); return; }
    socket.emit("demo", { start: !running }, (res) => {
      if (res && !res.ok && !running) toast("Демото не може да започне");
    });
  });

  /* ---------------- posture ("Още") ---------------- */
  const POSTURE_SLIDERS = [
    { cmd: "Euler", key: "y", label: "Наклон напред/назад", unit: "рад" },
    { cmd: "Euler", key: "x", label: "Наклон встрани", unit: "рад" },
    { cmd: "BodyHeight", key: "data", label: "Височина", unit: "м" },
  ];
  const postureEls = {};

  function buildPosture() {
    const lim = (config.posture && config.posture.limits) || {};
    const wrap = $("postureSliders");
    wrap.textContent = "";
    const rows = POSTURE_SLIDERS.filter((p) => lim[p.cmd]);
    $("morePanel").hidden = rows.length === 0;
    for (const p of rows) {
      const [lo, hi] = lim[p.cmd][p.key];
      const row = document.createElement("label");
      row.className = "slider";
      row.innerHTML = "<span></span><output></output><input type=\"range\">";
      row.children[0].textContent = p.label;
      const input = row.querySelector("input");
      Object.assign(input, { min: lo, max: hi, step: 0.01, value: 0 });
      const out = row.querySelector("output");
      const fmt = (v) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)} ${p.unit}`;
      out.textContent = fmt(0);
      input.addEventListener("input", () => { out.textContent = fmt(+input.value); });
      input.addEventListener("change", () => sendPosture(p.cmd)); // on release: one awaited command
      postureEls[`${p.cmd}.${p.key}`] = { input, out, fmt };
      wrap.appendChild(row);
    }
  }

  function sendPosture(cmd) {
    const param = {};
    for (const [id, el] of Object.entries(postureEls)) {
      const [c, key] = id.split(".");
      if (c === cmd) param[key] = +el.input.value;
    }
    socket.emit("posture", { name: cmd, param }, (res) => { if (res && !res.ok) toast("Командата е отказана"); });
  }

  $("postureReset").addEventListener("click", () => {
    for (const el of Object.values(postureEls)) { el.input.value = 0; el.out.textContent = el.fmt(0); }
    socket.emit("posture", { reset: true });
  });

  /* ---------------- actions ---------------- */
  const GROUP_TITLES = { posture: "Поза", tricks: "Трикове" };

  function renderActions() {
    const root = $("actions");
    root.textContent = "";
    actionLabels = { FollowStop: "Спри следването" };
    const grids = {};
    // digit keys follow display order: 1…0 = the first ten buttons
    config.actions.forEach((a, i) => {
      const group = a.group || "posture";
      if (!grids[group]) {
        const h = document.createElement("h3");
        h.className = "act-group";
        h.textContent = GROUP_TITLES[group] || group;
        const grid = document.createElement("div");
        grid.className = "actions";
        grid.dataset.group = group;
        root.append(h, grid);
        grids[group] = grid;
      }
      const wrap = grids[group];
      actionLabels[a.name] = a.label;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "act";
      b.dataset.name = a.name;
      b.innerHTML = `<svg class="ic"><use href="#i-${a.icon}"/></svg><span class="act-label"></span>` +
        (DIGITS[i] ? `<kbd>${DIGITS[i]}</kbd>` : "");
      b.querySelector(".act-label").textContent = a.label;
      b.addEventListener("click", () => runAction(a.name));
      wrap.appendChild(b);
    });
    syncActionsEnabled();
  }

  function syncActionsEnabled() {
    const off = linkState !== "connected";
    document.querySelectorAll(".act").forEach((b) => { b.disabled = off; });
  }

  function runAction(name) {
    const btn = document.querySelector(`.act[data-name="${name}"]`);
    if (linkState !== "connected") { toast("Роботът не е свързан"); return; }
    keys.clear(); moveStick.release(); turnStick.release(); streaming = false;
    if (btn) flash(btn);
    socket.emit("action", { name }, (res) => {
      if (res && !res.ok) toast(`Отказано: ${actionLabels[name] || name}`);
    });
  }

  /* ---------------- AI ---------------- */
  document.querySelectorAll(".switch").forEach((sw) => {
    sw.addEventListener("change", () => {
      sw._userAt = performance.now();
      socket.emit("ai", { mode: sw.dataset.mode, on: sw.checked });
      sw.closest(".ai-mode").dataset.on = String(sw.checked);
    });
  });

  function renderLegend() {
    const ul = $("gLegend");
    ul.textContent = "";
    for (const [g, a] of Object.entries(config.gesture_mapping || {})) {
      const li = document.createElement("li");
      li.dataset.g = g;
      li.innerHTML = "<span></span><span></span>";
      li.children[0].textContent = GESTURE_BG[g] || g;
      li.children[1].textContent = actionLabels[a] || a;
      ul.appendChild(li);
    }
    const streak = $("gStreak");
    streak.textContent = "";
    for (let i = 0; i < 8; i++) streak.appendChild(document.createElement("i"));
  }

  function ago(ts) {
    const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
    return s < 60 ? `преди ${s} с` : `преди ${Math.floor(s / 60)} мин`;
  }

  const AI_BOX = { gestures: "aiGestures", objects: "aiObjects", follow: "aiFollow" };

  function renderAI(ai) {
    for (const [mode, st] of Object.entries(ai || {})) {
      const box = $(AI_BOX[mode]);
      if (!box) continue;
      const sw = box.querySelector(".switch");
      if (!sw._userAt || performance.now() - sw._userAt > 1500) {
        sw.checked = st.enabled;
        box.dataset.on = String(st.enabled);
      }
      if (mode === "gestures") renderGestures(st);
      else if (mode === "follow") renderFollow(st);
      else renderObjects(st);
    }
    // while following, the open palm stops following instead of its mapped action
    const palm = $("gLegend").querySelector('li[data-g="Open_Palm"] span:last-child');
    if (palm) {
      const following = !!(ai && ai.follow && ai.follow.enabled);
      palm.textContent = following ? actionLabels.FollowStop : (actionLabels[config.gesture_mapping.Open_Palm] || "");
    }
  }

  /* ---------------- follow ---------------- */
  const FOLLOW_STATUS = {
    locked: "Целта е заключена", too_close: "Твърде близо", searching: "Търся човек…",
    paused: "Пауза за действие", loading: "Зареждане на модела…", off: "Изключено",
  };
  const SLIDERS = [
    { key: "k_yaw", label: "Завиване K_yaw", step: 0.05, fmt: (v) => v.toFixed(2) },
    { key: "k_x", label: "Напред K_x", step: 0.05, fmt: (v) => v.toFixed(2) },
    { key: "target_h", label: "Целева височина", step: 0.01, fmt: (v) => v.toFixed(2) },
    { key: "max_vx", label: "Макс. vx, м/с", step: 0.01, fmt: (v) => v.toFixed(2) },
    { key: "max_yaw", label: "Макс. ω, рад/с", step: 0.05, fmt: (v) => v.toFixed(2) },
  ];
  const sliderEls = {};
  let sliderTouchedAt = 0;

  function buildSliders(limits, cfg) {
    const wrap = $("fSliders");
    if (wrap.childElementCount) return;
    for (const sd of SLIDERS) {
      const [lo, hi] = limits[sd.key];
      const row = document.createElement("label");
      row.className = "slider";
      row.innerHTML = `<span></span><output></output><input type="range">`;
      row.children[0].textContent = sd.label;
      const input = row.querySelector("input");
      Object.assign(input, { min: lo, max: hi, step: sd.step, value: cfg[sd.key] });
      const out = row.querySelector("output");
      out.textContent = sd.fmt(cfg[sd.key]);
      let t = null;
      input.addEventListener("input", () => {
        sliderTouchedAt = performance.now();
        out.textContent = sd.fmt(+input.value);
        clearTimeout(t);
        t = setTimeout(() => socket.emit("follow_config", { [sd.key]: +input.value }), 80);
      });
      sliderEls[sd.key] = { input, out, fmt: sd.fmt };
      wrap.appendChild(row);
    }
  }

  function renderFollow(st) {
    if (st.limits && st.config) buildSliders(st.limits, st.config);
    if (st.config && performance.now() - sliderTouchedAt > 1500) {
      for (const [k, el] of Object.entries(sliderEls)) {
        if (document.activeElement === el.input) continue;
        el.input.value = st.config[k];
        el.out.textContent = el.fmt(st.config[k]);
      }
    }
    const pill = $("fStatus");
    pill.dataset.s = st.status;
    pill.textContent = st.error ? "Грешка в модела" : (FOLLOW_STATUS[st.status] || st.status);
    $("fFps").textContent = `AI ${Math.round(st.fps || 0)} fps`;
    const f = (x) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(2);
    $("fVx").textContent = (st.vx || 0).toFixed(2);
    $("fYaw").textContent = f(st.vyaw || 0);
    $("fVx").parentElement.dataset.active = String(st.vx > 0);
    $("fYaw").parentElement.dataset.active = String(st.vyaw !== 0);
    $("fSlow").hidden = !st.slow;
  }

  function renderGestures(st) {
    const g = st.gesture;
    const has = g && g !== "None";
    $("gLabel").textContent = st.error ? "Грешка" : !st.ready ? "Зареждане на модела…" : has ? (GESTURE_BG[g] || g) : "Няма жест";
    $("gAction").textContent = has && st.action ? `→ ${actionLabels[st.action] || st.action}` : "";
    const n = has && st.action ? st.streak : 0;
    const bars = $("gStreak").children;
    for (let i = 0; i < bars.length; i++) bars[i].dataset.on = String(i < n);
    $("gStreak").dataset.cool = String(st.cooldown > 0);
    const last = $("gLast");
    if (st.error) {
      last.textContent = st.error;
    } else if (st.last_trigger) {
      const t = st.last_trigger;
      last.innerHTML = "Последно: <b></b> · <span></span>";
      last.querySelector("b").textContent = `${GESTURE_BG[t.gesture] || t.gesture} → ${actionLabels[t.action] || t.action}`;
      last.querySelector("span").textContent = st.cooldown > 0 ? `пауза ${st.cooldown.toFixed(0)} с` : ago(t.at);
    } else {
      last.textContent = "Задръж жест пред камерата";
    }
    $("gLegend").querySelectorAll("li").forEach((li) => { li.dataset.hit = String(li.dataset.g === g); });
  }

  function renderObjects(st) {
    const ul = $("oList");
    ul.textContent = "";
    const add = (text, cls) => { const li = document.createElement("li"); if (cls) li.className = cls; li.textContent = text; ul.appendChild(li); return li; };
    if (st.error) { add(st.error, "muted"); return; }
    if (!st.ready) { add("Зареждане на модела…", "muted"); return; }
    if (!st.objects.length) { add("Нищо не е открито", "muted"); return; }
    for (const o of st.objects) {
      const li = add(o.label);
      const b = document.createElement("b");
      b.textContent = `×${o.count}`;
      li.appendChild(b);
    }
  }

  /* ---------------- telemetry ---------------- */
  const LINK_TEXT = { connected: "Свързан", connecting: "Свързване…", error: "Няма връзка", disconnected: "Няма връзка" };

  function setAlert(text, kind) {
    const a = $("alert");
    if (!text) { a.hidden = true; return; }
    a.hidden = false;
    a.dataset.kind = kind || "warn";
    $("alertText").textContent = text;
  }

  function renderTelemetry(t) {
    if (linkState !== t.state) {
      linkState = t.state;
      syncActionsEnabled();
    }
    app.dataset.link = t.state;
    $("linkText").textContent = LINK_TEXT[t.state] || t.state;
    $("linkBtnText").textContent = t.state === "connected" || t.state === "connecting" ? "Прекъсни" : "Свържи";
    $("simTag").hidden = !t.sim;

    if (!socketUp) setAlert("Няма връзка със сървъра. Стартиран ли е controller.app?", "danger");
    else if (t.state === "error") setAlert(`${t.error}. Опитвам отново…`, "danger");
    else if (t.state === "disconnected" && t.error) setAlert(t.error, "warn");
    else setAlert(null);

    const bat = $("statBattery");
    if (typeof t.battery === "number") {
      $("batteryText").textContent = `${Math.round(t.battery)}%`;
      $("batteryFill").style.width = `${Math.max(0, Math.min(100, t.battery))}%`;
      bat.dataset.level = t.battery < 15 ? "critical" : t.battery < 30 ? "low" : "ok";
    } else {
      $("batteryText").textContent = "—";
      $("batteryFill").style.width = "0";
      bat.dataset.level = "none";
    }
    $("modeText").textContent = t.mode || "—";
    $("postureText").textContent = t.posture_label || "—";
    $("postureText").dataset.chain = String(!!t.chain);
    // OSD shows what the robot is being commanded; when the operator is idle that may be follow mode
    if (!streaming && t.velocity) renderVel(t.velocity);
    $("fpsText").textContent = String(t.fps || 0);
    $("cmdText").textContent = t.last_command || "—";
    const code = $("codeText");
    if (t.last_command) {
      code.textContent = String(t.last_code);
      code.dataset.ok = String(t.last_code === 0);
    } else code.textContent = "";

    const videoOn = t.fps > 0;
    app.dataset.video = videoOn ? "on" : "off";
    if (!videoOn) {
      $("novideoText").textContent = t.state === "connecting" ? "Свързване с робота…"
        : t.state === "connected" ? "Чакам видео…" : "Няма видео";
    }
    renderAI(t.ai);
    renderDemo(t.demo);
  }

  /* ---------------- video ---------------- */
  const video = $("video");
  function startVideo() { video.src = `/video?t=${Date.now()}`; }
  video.addEventListener("error", () => setTimeout(startVideo, 1000));

  /* ---------------- robot link button ---------------- */
  $("linkBtn").addEventListener("click", () => {
    const connect = !(linkState === "connected" || linkState === "connecting");
    socket.emit("robot", { connect });
  });

  /* ---------------- socket ---------------- */
  let everConnected = false;
  socket.on("connect", () => {
    socketUp = true; setAlert(null);
    if (everConnected) startVideo(); // server restarted: reopen the MJPEG stream
    else socket.emit("ai_all_off"); // page load: every AI mode starts off, turned on by hand
    everConnected = true;
  });
  socket.on("disconnect", () => {
    socketUp = false;
    streaming = false;
    setAlert("Няма връзка със сървъра. Стартиран ли е controller.app?", "danger");
    app.dataset.link = "disconnected";
    $("linkText").textContent = "Няма връзка";
  });
  socket.on("config", (c) => {
    config = c;
    if (Array.isArray(c.speed_presets) && c.speed_presets.length) {
      speeds = c.speed_presets.map((p) => ({ lin: p.linear, yaw: p.yaw }));
      segButtons.forEach((b, i) => {
        const p = c.speed_presets[i];
        if (p) { b.textContent = p.label; b.title = `${p.linear} м/с · ${p.yaw} рад/с`; }
      });
    }
    renderActions();
    renderLegend();
    renderDemoSteps();
    buildPosture();
  });
  socket.on("telemetry", renderTelemetry);
  socket.on("notice", (n) => { if (n && n.text) toast(n.text); });
  socket.on("log", addFeed);
  socket.on("log_history", (items) => { (items || []).forEach(addFeed); });

  renderVel(lastVel);
})();
