/* Roomba RC — cliente WebSocket.
 *
 * Princípios:
 *  - Último comando vence: enviamos drive continuamente (~10 Hz) enquanto um
 *    controle está ativo. O servidor sobrescreve o alvo (nunca enfileira).
 *  - Heartbeat: se pararmos de enviar, o servidor para o robô (timeout ~0.3s).
 *  - Funciona com toque E mouse.
 */

(function () {
  "use strict";

  var MAX_VEL = 500;
  var MIN_VEL = 50;
  var SEND_HZ = 10;
  var SEND_INTERVAL = 1000 / SEND_HZ;

  // ── WebSocket com auto-reconexão ──────────────────────────────────────────
  var ws = null;
  var wsReady = false;
  var connEl = document.getElementById("conn");

  function wsUrl() {
    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    return proto + "//" + location.host + "/ws";
  }

  function connect() {
    ws = new WebSocket(wsUrl());

    ws.onopen = function () {
      wsReady = true;
      connEl.textContent = "online";
      connEl.className = "conn on";
    };

    ws.onclose = function () {
      wsReady = false;
      connEl.textContent = "offline";
      connEl.className = "conn off";
      setTimeout(connect, 1000); // reconecta
    };

    ws.onerror = function () {
      try { ws.close(); } catch (e) {}
    };

    ws.onmessage = function (ev) {
      var data;
      try { data = JSON.parse(ev.data); } catch (e) { return; }
      if (data.type === "battery") updateBattery(data);
      else if (data.type === "role") updateRole(data.driver);
    };
  }

  function send(obj) {
    if (wsReady && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    }
  }

  // ── Single-driver lock: motorista x espectador ────────────────────────────
  var isDriver = true;
  var roleBanner = document.getElementById("role-banner");
  var roleText = document.getElementById("role-text");

  function updateRole(driver) {
    isDriver = !!driver;
    if (isDriver) {
      roleBanner.classList.add("hidden");
      roleText.textContent = "";
    } else {
      stopDrive();
      roleBanner.classList.remove("hidden");
      roleText.textContent = "Espectador — outro cliente está no controle";
    }
    document.body.classList.toggle("spectator", !isDriver);
  }

  document.getElementById("btn-claim").addEventListener("click", function () {
    send({ type: "claim" });
  });

  // ── HUD bateria ───────────────────────────────────────────────────────────
  var batPct = document.getElementById("bat-pct");
  var batVolt = document.getElementById("bat-volt");
  var batCurr = document.getElementById("bat-curr");
  var batState = document.getElementById("bat-state");

  function updateBattery(b) {
    if (!b.ok) {
      batPct.textContent = "N/D";
      batPct.className = "bat-pct red";
      batVolt.textContent = "-- V";
      batCurr.textContent = "-- mA";
      batState.textContent = "sem sensor";
      return;
    }
    var pct = b.percent;
    batPct.textContent = pct.toFixed(0) + "%";
    var cls = pct >= 60 ? "green" : (pct >= 25 ? "yellow" : "red");
    batPct.className = "bat-pct " + cls;
    batVolt.textContent = b.voltage.toFixed(1) + " V";
    batCurr.textContent = b.current + " mA";
    batState.textContent = b.state;
  }

  // ── Loop de envio contínuo (~10 Hz) ───────────────────────────────────────
  // Mantém o alvo atual; enquanto active=true reenviamos para o heartbeat.
  var curLeft = 0;
  var curRight = 0;
  var active = false;

  function setDrive(left, right) {
    if (!isDriver) return;            // espectador não comanda
    curLeft = Math.round(left);
    curRight = Math.round(right);
    active = true;
  }

  function stopDrive() {
    curLeft = 0;
    curRight = 0;
    active = false;
    send({ type: "stop" });
  }

  setInterval(function () {
    if (active && isDriver) send({ type: "drive", left: curLeft, right: curRight });
  }, SEND_INTERVAL);

  // ── Seletor de modo ───────────────────────────────────────────────────────
  var dpadMode = document.getElementById("dpad-mode");
  var joyMode = document.getElementById("joy-mode");
  document.querySelectorAll(".mode-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll(".mode-btn").forEach(function (b) {
        b.classList.remove("active");
      });
      btn.classList.add("active");
      stopDrive();
      if (btn.dataset.mode === "dpad") {
        dpadMode.classList.remove("hidden");
        joyMode.classList.add("hidden");
      } else {
        joyMode.classList.remove("hidden");
        dpadMode.classList.add("hidden");
      }
    });
  });

  // ── Modo D-PAD ────────────────────────────────────────────────────────────
  var vel = 150;
  var velSlider = document.getElementById("vel-slider");
  var velVal = document.getElementById("vel-val");
  velSlider.addEventListener("input", function () {
    vel = parseInt(velSlider.value, 10);
    velVal.textContent = vel;
    send({ type: "vel", value: vel });
  });

  function dpadVector(dir) {
    switch (dir) {
      case "fwd":   return [vel, vel];
      case "back":  return [-vel, -vel];
      case "left":  return [-vel, vel];
      case "right": return [vel, -vel];
      default:      return [0, 0];
    }
  }

  document.querySelectorAll(".dbtn").forEach(function (btn) {
    var dir = btn.dataset.dir;

    if (dir === "stop") {
      btn.addEventListener("click", function () { stopDrive(); });
      return;
    }

    var press = function (e) {
      e.preventDefault();
      var v = dpadVector(dir);
      setDrive(v[0], v[1]);
      send({ type: "drive", left: v[0], right: v[1] }); // envia já no toque
    };
    var release = function (e) {
      if (e) e.preventDefault();
      stopDrive();
    };

    // Toque
    btn.addEventListener("touchstart", press, { passive: false });
    btn.addEventListener("touchend", release, { passive: false });
    btn.addEventListener("touchcancel", release, { passive: false });
    // Mouse
    btn.addEventListener("mousedown", press);
    btn.addEventListener("mouseup", release);
    btn.addEventListener("mouseleave", function (e) {
      if (active) release(e);
    });
  });

  // ── Modo JOYSTICK (mixagem differential / arcade) ─────────────────────────
  var base = document.getElementById("joy-base");
  var stick = document.getElementById("joy-stick");
  var dragging = false;
  var radius = 0; // raio máximo de deslocamento do thumbstick

  function joyStart(clientX, clientY) {
    dragging = true;
    radius = base.clientWidth / 2 - stick.clientWidth / 2;
    joyMove(clientX, clientY);
  }

  function joyMove(clientX, clientY) {
    if (!dragging) return;
    var rect = base.getBoundingClientRect();
    var cx = rect.left + rect.width / 2;
    var cy = rect.top + rect.height / 2;
    var dx = clientX - cx;
    var dy = clientY - cy;

    // Limita ao raio do círculo.
    var dist = Math.sqrt(dx * dx + dy * dy);
    if (dist > radius) {
      dx = (dx / dist) * radius;
      dy = (dy / dist) * radius;
    }

    // Posiciona o thumbstick.
    stick.style.transform =
      "translate(calc(-50% + " + dx + "px), calc(-50% + " + dy + "px))";

    // Normaliza para [-1, 1].
    var nx = dx / radius;       // direita = +
    var ny = dy / radius;       // baixo = +

    var forward = -ny;          // frente = -y
    var turn = nx;              // virar = x

    var left = (forward + turn) * MAX_VEL;
    var right = (forward - turn) * MAX_VEL;

    left = Math.max(-MAX_VEL, Math.min(MAX_VEL, left));
    right = Math.max(-MAX_VEL, Math.min(MAX_VEL, right));

    setDrive(left, right);
  }

  function joyEnd() {
    if (!dragging) return;
    dragging = false;
    stick.style.transform = "translate(-50%, -50%)";
    stopDrive();
  }

  // Toque
  base.addEventListener("touchstart", function (e) {
    e.preventDefault();
    var t = e.changedTouches[0];
    joyStart(t.clientX, t.clientY);
  }, { passive: false });
  base.addEventListener("touchmove", function (e) {
    e.preventDefault();
    var t = e.changedTouches[0];
    joyMove(t.clientX, t.clientY);
  }, { passive: false });
  base.addEventListener("touchend", function (e) {
    e.preventDefault(); joyEnd();
  }, { passive: false });
  base.addEventListener("touchcancel", function (e) {
    e.preventDefault(); joyEnd();
  }, { passive: false });

  // Mouse
  base.addEventListener("mousedown", function (e) {
    e.preventDefault();
    joyStart(e.clientX, e.clientY);
  });
  window.addEventListener("mousemove", function (e) {
    if (dragging) joyMove(e.clientX, e.clientY);
  });
  window.addEventListener("mouseup", function () {
    if (dragging) joyEnd();
  });

  // ── Botões globais ────────────────────────────────────────────────────────
  document.getElementById("btn-stop").addEventListener("click", function () {
    stopDrive();
  });
  document.getElementById("btn-dock").addEventListener("click", function () {
    if (!isDriver) return;
    active = false;
    curLeft = 0;
    curRight = 0;
    send({ type: "dock" });
  });

  // Para por segurança quando a aba perde foco / é escondida.
  window.addEventListener("blur", stopDrive);
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) stopDrive();
  });

  // ── Inicializa ────────────────────────────────────────────────────────────
  connect();
})();
