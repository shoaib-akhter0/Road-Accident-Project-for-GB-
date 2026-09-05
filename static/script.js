const statusPill = document.getElementById("status-pill");
const statusLabel = document.getElementById("status-label");
const videoFrame = document.getElementById("video-frame");
const videoStream = document.getElementById("video-stream");
const videoPercent = document.getElementById("video-percent");
const camCard1 = document.getElementById("cam-card-1");
const cam1Badge = document.getElementById("cam1-badge");
const cam1BadgeText = document.getElementById("cam1-badge-text");
const recBadge = document.getElementById("rec-badge");
const frozenBadge = document.getElementById("frozen-badge");
const readoutIdle = document.getElementById("readout-idle");
const readoutActive = document.getElementById("readout-active");
const metricPercent = document.getElementById("metric-percent");
const metricBarFill = document.getElementById("metric-bar-fill");
const metricSpikes = document.getElementById("metric-spikes");
const readoutTime = document.getElementById("readout-time");
const eventEmpty = document.getElementById("event-empty");
const eventDetail = document.getElementById("event-detail");
const eventPhoto = document.getElementById("event-photo");
const eventTime = document.getElementById("event-time");
const alertOverlay = document.getElementById("alert-overlay");
const alertPhoto = document.getElementById("alert-photo");
const alertTime = document.getElementById("alert-time");
const alertFeedback = document.getElementById("alert-feedback");
const btnWhatsapp = document.getElementById("btn-whatsapp");
const btnDismiss = document.getElementById("btn-dismiss");

let lastAccidentPercent = 0;
let alertRequestInFlight = false;
let alertSentForCurrentEvent = false;
const btnPause = document.getElementById("btn-pause");
const btnResume = document.getElementById("btn-resume");
const btnStop = document.getElementById("btn-stop");
const statUptime = document.getElementById("stat-uptime");
const statAlerts = document.getElementById("stat-alerts");
const statCamera = document.getElementById("stat-camera");
const clockEl = document.getElementById("clock");

let alertShownFor = null; // last_alert_time we've already surfaced a modal for
let alertCount = 0;       // alerts seen during this browser session
const startTime = Date.now();

// ------------------------------------------------------------
// CLOCK + UPTIME
// ------------------------------------------------------------
function updateClock() {
  clockEl.textContent = new Date().toLocaleTimeString("en-GB");
}
setInterval(updateClock, 1000);
updateClock();

function updateUptime() {
  const s = Math.floor((Date.now() - startTime) / 1000);
  const hh = String(Math.floor(s / 3600)).padStart(2, "0");
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  statUptime.textContent = `${hh}:${mm}:${ss}`;
}
setInterval(updateUptime, 1000);
updateUptime();

// ------------------------------------------------------------
// STATUS UI
// ------------------------------------------------------------
function setMonitoringUI() {
  statusPill.classList.remove("alert");
  statusPill.classList.add("monitoring");
  statusLabel.textContent = "MONITORING";
  videoFrame.classList.remove("alert-active");

  // CAM 01 card badge back to the all-clear state
  camCard1.classList.remove("cam-card-alert");
  cam1Badge.classList.remove("cam-badge-alert");
  cam1Badge.classList.add("cam-badge-ok");
  cam1BadgeText.textContent = "NO ACCIDENT";

  // Readings only exist while an accident is active
  readoutIdle.classList.remove("hidden");
  readoutActive.classList.add("hidden");
  videoPercent.classList.add("hidden");
}

function setAlertUI() {
  statusPill.classList.remove("monitoring");
  statusPill.classList.add("alert");
  statusLabel.textContent = "ACCIDENT DETECTED";
  videoFrame.classList.add("alert-active");

  // CAM 01 card badge flips to the alert state
  camCard1.classList.add("cam-card-alert");
  cam1Badge.classList.remove("cam-badge-ok");
  cam1Badge.classList.add("cam-badge-alert");
  cam1BadgeText.textContent = "ACCIDENT DETECTED";

  readoutIdle.classList.add("hidden");
  readoutActive.classList.remove("hidden");
  videoPercent.classList.remove("hidden");
}

// ------------------------------------------------------------
// STATUS POLLING
// ------------------------------------------------------------
async function poll() {
  try {
    const res = await fetch("/status");
    const data = await res.json();

    if (data.status === "alert") {
      setAlertUI();

      lastAccidentPercent = Number(data.accident_percent || 0);

      // Live readings — visible only during an accident
      metricPercent.textContent = data.accident_percent.toFixed(1) + "%";
      metricBarFill.style.width = Math.min(data.accident_percent, 100) + "%";
      metricBarFill.style.background = "var(--alert-red)";
      metricSpikes.textContent = data.spike_count;
      videoPercent.textContent = "ALERT: " + data.accident_percent.toFixed(1) + "%";

      if (data.last_alert_photo) {
        readoutTime.textContent = data.last_alert_time || "—";
        eventEmpty.classList.add("hidden");
        eventDetail.classList.remove("hidden");
        eventPhoto.src = "/accident_photos/" + data.last_alert_photo;
        eventTime.textContent = data.last_alert_time || "—";
      }

      // New alert -> count it + open the modal once
      if (alertShownFor !== data.last_alert_time) {
        alertShownFor = data.last_alert_time;
        alertCount += 1;
        statAlerts.textContent = alertCount;
        alertPhoto.src = data.last_alert_photo ? "/accident_photos/" + data.last_alert_photo : "";
        alertTime.textContent = data.last_alert_time || "—";
        alertFeedback.textContent = "";
        alertFeedback.classList.remove("error");
        alertSentForCurrentEvent = false;
        alertOverlay.classList.remove("hidden");
      }
    } else {
      setMonitoringUI();
      alertOverlay.classList.add("hidden");
    }
  } catch (err) {
    console.error("status poll failed", err);
  }
}

setInterval(poll, 700);
poll();

// ------------------------------------------------------------
// CAMERA CONTROLS (server-side pause: screen stops, detection
// keeps running armed in the background)
// ------------------------------------------------------------
function showFrozen(label) {
  recBadge.classList.add("hidden");
  frozenBadge.textContent = label;
  frozenBadge.classList.remove("hidden");
}

function setCameraStat(text, mode) {
  statCamera.textContent = text;
  statCamera.className = "stat-value stat-value-" + mode;
}

btnPause.addEventListener("click", async () => {
  await fetch("/pause", { method: "POST" });
  showFrozen("\u275A\u275A FEED PAUSED");
  setCameraStat("PAUSED", "paused");
});

btnStop.addEventListener("click", async () => {
  await fetch("/pause", { method: "POST" });
  showFrozen("\u25A0 FEED STOPPED");
  setCameraStat("STOPPED", "stopped");
});

btnResume.addEventListener("click", async () => {
  await fetch("/play", { method: "POST" });
  frozenBadge.classList.add("hidden");
  recBadge.classList.remove("hidden");
  setCameraStat("LIVE", "live");
});

// ------------------------------------------------------------
// ALERT MODAL ACTIONS
// ------------------------------------------------------------
btnWhatsapp.addEventListener("click", async () => {
  if (alertRequestInFlight || alertSentForCurrentEvent) {
    return;
  }

  alertRequestInFlight = true;
  btnWhatsapp.disabled = true;
  btnWhatsapp.textContent = "Sending Alert...";
  alertFeedback.textContent = "Sending Alert...";
  alertFeedback.classList.remove("error");

  try {
    const message = `🚨 ACCIDENT ALERT! An accident has been detected by the Road Accident Detection System. Camera: CAM 01. Confidence: ${lastAccidentPercent.toFixed(1)}%. Please respond immediately.`;
    const captureUrl = alertPhoto.src ? new URL(alertPhoto.src, window.location.href).pathname : "";
    const res = await fetch("/api/send-alert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        detection_time: alertTime.textContent,
        capture_url: captureUrl,
        confidence: lastAccidentPercent.toFixed(1) + "%"
      })
    });
    const data = await res.json();

    if (data.success) {
      alertSentForCurrentEvent = true;
      alertFeedback.textContent = "✓ Alert Sent Successfully";
      btnWhatsapp.textContent = "✓ Alert Sent Successfully";
      alertFeedback.classList.remove("error");
      await fetch("/resume", { method: "POST" });
      alertOverlay.classList.add("hidden");
      setMonitoringUI();
      return;
    }

    alertFeedback.textContent = `✗ Alert Failed: ${data.message || "Email could not be sent."}`;
    alertFeedback.classList.add("error");
    btnWhatsapp.textContent = "✗ Alert Failed";
    btnWhatsapp.disabled = false;
  } catch (err) {
    alertFeedback.textContent = "✗ Alert Failed: Email could not be sent.";
    alertFeedback.classList.add("error");
    btnWhatsapp.textContent = "✗ Alert Failed";
    btnWhatsapp.disabled = false;
  } finally {
    alertRequestInFlight = false;
  }
});

btnDismiss.addEventListener("click", async () => {
  await fetch("/resume", { method: "POST" });
  alertOverlay.classList.add("hidden");
  setMonitoringUI();
});
