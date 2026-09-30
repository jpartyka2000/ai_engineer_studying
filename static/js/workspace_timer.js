/*
 * Countdown and workspace-health polling for workspace mode.
 *
 * The server owns the deadline. This only renders it, and re-syncs on an interval so
 * drift cannot accumulate. Deliberately NOT the `CountdownTimer` class in main.js,
 * which is unused dead code with hardcoded 30/60-second thresholds, M:SS formatting
 * that renders 3600s as "60:00", and no server sync at all.
 */
(function () {
  "use strict";

  var el = document.getElementById("ws-timer");
  if (!el) return;

  var display = document.getElementById("ws-timer-display");
  var banner = document.getElementById("ws-workspace-banner");
  var dirtyEl = document.getElementById("ws-dirty-count");
  var commitsEl = document.getElementById("ws-commit-count");
  var containersEl = document.getElementById("ws-containers");

  var remaining = parseInt(el.dataset.remaining, 10);
  var warnAt = parseInt(el.dataset.warnSeconds, 10) || 300;
  var dangerAt = parseInt(el.dataset.dangerSeconds, 10) || 60;
  var heartbeatUrl = el.dataset.heartbeatUrl;
  var pollEvery = (parseInt(el.dataset.pollSeconds, 10) || 15) * 1000;

  if (isNaN(remaining)) return;

  /* H:MM:SS at or above an hour; a 60-minute task must not render as "60:00". */
  function format(total) {
    if (total < 0) total = 0;
    var hours = Math.floor(total / 3600);
    var minutes = Math.floor((total % 3600) / 60);
    var seconds = total % 60;
    var mm = minutes < 10 && hours > 0 ? "0" + minutes : String(minutes);
    var ss = seconds < 10 ? "0" + seconds : String(seconds);
    return hours > 0 ? hours + ":" + mm + ":" + ss : mm + ":" + ss;
  }

  function render() {
    display.textContent = format(remaining);
    display.classList.remove("warning", "danger");
    if (remaining <= dangerAt) {
      display.classList.add("danger");
    } else if (remaining <= warnAt) {
      display.classList.add("warning");
    }
  }

  function finish(resultsUrl) {
    clearInterval(ticker);
    clearInterval(poller);
    display.textContent = format(0);
    display.classList.add("danger");
    window.location.href = resultsUrl || el.dataset.resultsUrl;
  }

  function tick() {
    remaining -= 1;
    if (remaining <= 0) {
      remaining = 0;
      render();
      /* Do not submit from here. The server has already ended the session; the next
       * poll confirms it and redirects. Trusting the client to end an attempt would
       * make the deadline negotiable. */
      return;
    }
    render();
  }

  function setContainers(containers) {
    if (!containersEl) return;
    if (!containers || !containers.length) {
      containersEl.textContent = "";
      return;
    }
    var unhealthy = containers.filter(function (c) {
      return c.state !== "running";
    });
    containersEl.textContent = unhealthy.length
      ? unhealthy.length + " container(s) not running"
      : containers.length + " container(s) running";
    containersEl.className = unhealthy.length
      ? "text-xs text-red-600"
      : "text-xs text-green-600";
  }

  function sync() {
    fetch(heartbeatUrl, { headers: { "X-Requested-With": "fetch" } })
      .then(function (response) {
        if (!response.ok) throw new Error("heartbeat " + response.status);
        return response.json();
      })
      .then(function (data) {
        if (data.is_time_up || data.status !== "in_progress") {
          finish(data.results_url);
          return;
        }
        /* The server is authoritative: adopt its number rather than our own. */
        remaining = data.time_remaining;
        render();

        if (dirtyEl) dirtyEl.textContent = data.dirty_files;
        if (commitsEl) commitsEl.textContent = data.commits;
        setContainers(data.containers);

        if (banner) {
          banner.classList.toggle("hidden", data.workspace_ok !== false);
        }
      })
      .catch(function (error) {
        /* A failed poll must not stop the clock; the local countdown carries on and
         * the next poll corrects any drift. */
        if (window.console) console.warn("workspace heartbeat failed:", error);
      });
  }

  render();
  var ticker = setInterval(tick, 1000);
  var poller = setInterval(sync, pollEvery);
  sync();
})();
