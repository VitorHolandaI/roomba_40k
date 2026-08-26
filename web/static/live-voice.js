/* Interfone PCM de baixa latência: navegador -> WebSocket -> aplay no Pi. */

(function () {
  "use strict";

  var TARGET_RATE = 16000;
  var MAX_SOCKET_BACKLOG = 2048;
  var button = document.getElementById("voice-button");
  var status = document.getElementById("voice-status");
  var socket = null;
  var audioContext = null;
  var mediaStream = null;
  var sourceNode = null;
  var processorNode = null;
  var active = false;
  var starting = false;

  function voiceWsUrl() {
    var protocol = location.protocol === "https:" ? "wss:" : "ws:";
    return protocol + "//" + location.host + "/voice-ws";
  }

  function setState(state, message) {
    button.disabled = state === "starting" || state === "blocked";
    button.classList.toggle("active", state === "active");
    button.textContent = state === "active" ? "PARAR VOZ" : "FALAR AO VIVO";
    status.textContent = message;
  }

  function toPcm16(input, inputRate) {
    var ratio = inputRate / TARGET_RATE;
    var output = new Int16Array(Math.floor(input.length / ratio));
    for (var i = 0; i < output.length; i += 1) {
      var first = Math.floor(i * ratio);
      var last = Math.max(first + 1, Math.floor((i + 1) * ratio));
      var sum = 0;
      for (var j = first; j < last && j < input.length; j += 1) sum += input[j];
      var sample = Math.max(-1, Math.min(1, sum / (last - first)));
      output[i] = sample < 0 ? sample * 32768 : sample * 32767;
    }
    return output.buffer;
  }

  function disconnectAudioGraph() {
    if (processorNode) processorNode.disconnect();
    if (sourceNode) sourceNode.disconnect();
    if (mediaStream) {
      mediaStream.getTracks().forEach(function (track) { track.stop(); });
    }
    if (audioContext) audioContext.close();
    processorNode = null;
    sourceNode = null;
    mediaStream = null;
    audioContext = null;
  }

  function stopVoice(message) {
    active = false;
    starting = false;
    disconnectAudioGraph();
    if (socket) {
      socket.onclose = null;
      socket.close();
    }
    socket = null;
    setState("idle", message || "Toque para abrir o microfone");
  }

  function connectVoiceSocket() {
    return new Promise(function (resolve, reject) {
      socket = new WebSocket(voiceWsUrl());
      var timeout = setTimeout(function () { reject(new Error("Servidor de voz não respondeu")); }, 5000);
      socket.addEventListener("message", function (event) {
        var message;
        try { message = JSON.parse(event.data); } catch (_error) { return; }
        if (message.type === "ready") {
          clearTimeout(timeout);
          resolve();
        } else if (message.type === "error") {
          clearTimeout(timeout);
          reject(new Error(message.message));
        }
      });
      socket.addEventListener("error", function () {
        clearTimeout(timeout);
        reject(new Error("Falha no WebSocket de voz"));
      });
      socket.addEventListener("close", function () {
        if (active) stopVoice("Interfone desconectado");
        else {
          clearTimeout(timeout);
          reject(new Error("WebSocket de voz foi fechado"));
        }
      });
    });
  }

  async function connectAudioGraph() {
    var AudioContext = window.AudioContext || window.webkitAudioContext;
    audioContext = new AudioContext({ latencyHint: "interactive", sampleRate: TARGET_RATE });
    await audioContext.resume();
    sourceNode = audioContext.createMediaStreamSource(mediaStream);
    processorNode = audioContext.createScriptProcessor(512, 1, 1);
    processorNode.onaudioprocess = function (event) {
      if (!active || !socket || socket.readyState !== WebSocket.OPEN) return;
      if (socket.bufferedAmount > MAX_SOCKET_BACKLOG) return;
      var samples = event.inputBuffer.getChannelData(0);
      socket.send(toPcm16(samples, audioContext.sampleRate));
    };
    sourceNode.connect(processorNode);
    processorNode.connect(audioContext.destination);
  }

  async function startVoice() {
    if (starting || active) return;
    starting = true;
    setState("starting", "Abrindo canal ao vivo...");
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      await connectAudioGraph();
      await connectVoiceSocket();
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        throw new Error("WebSocket de voz foi fechado");
      }
      active = true;
      setState("active", "Transmitindo ao vivo para o Raspberry Pi");
    } catch (error) {
      stopVoice(error.message || "Não foi possível abrir o microfone");
    } finally {
      starting = false;
    }
  }

  button.addEventListener("click", function () {
    if (active) stopVoice();
    else startVoice();
  });
  window.addEventListener("beforeunload", function () { stopVoice(); });

  var AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!window.isSecureContext || !navigator.mediaDevices) {
    setState("blocked", "Abra esta página por HTTPS para liberar o microfone");
  } else if (!AudioContext || !AudioContext.prototype.createScriptProcessor) {
    setState("blocked", "Este navegador não suporta o interfone ao vivo");
  }
})();
