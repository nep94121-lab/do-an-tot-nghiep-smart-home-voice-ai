"""Benchmark script for R3: Optimistic UI & Latency Optimization on /app.
Measures DOM toggle latency (before vs after) using Playwright Chromium and performance.now().
"""
from __future__ import annotations

import json
import pathlib
import threading
import time
import uvicorn
import sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright
from simulator.server import app


def run_benchmark(port: int = 8996) -> dict:
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(1.5)

    metrics = {}
    try:
        with sync_playwright() as p:
            # Use installed system Chrome
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(f"http://127.0.0.1:{port}/app")

            # Authenticate into /app
            page.evaluate("""() => {
                sessionStorage.setItem('mobileLoggedIn', '1');
                sessionStorage.setItem('mobileLoggedInEmail', 'nep94121@gmail.com');
                showMobileMainContent();
            }""")
            page.wait_for_selector("#mobileMainContent:not([hidden])", timeout=5000)

            # Switch to Devices Tab
            page.click("#mobileNavTabDevices")
            page.wait_for_selector('#devGrid [data-device-id="living_room_light"]', timeout=5000)

            # 1. Measure Optimistic In-Place UI Latency (<16ms target)
            optimistic_trials = []
            for _ in range(5):
                trial = page.evaluate("""() => {
                    const card = document.querySelector('#devGrid [data-device-id="living_room_light"]');
                    const initialClass = card.className;
                    const t0 = performance.now();
                    card.click();
                    const t1 = performance.now();
                    const immediateClass = card.className;
                    return {
                        durationMs: t1 - t0,
                        changed: initialClass !== immediateClass,
                        initialClass,
                        immediateClass
                    };
                }""")
                optimistic_trials.append(trial["durationMs"])
                time.sleep(0.3)

            # 2. Measure Server Roundtrip Baseline Latency (Non-optimistic network roundtrip)
            baseline_trials = []
            for _ in range(5):
                trial = page.evaluate("""async () => {
                    const t0 = performance.now();
                    const res = await fetch('/api/device', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ device_id: 'living_room_light', action: 'turn_on' }),
                    });
                    await res.json();
                    const t1 = performance.now();
                    return { durationMs: t1 - t0 };
                }""")
                baseline_trials.append(trial["durationMs"])
                time.sleep(0.3)

            browser.close()

            opt_avg = sum(optimistic_trials) / len(optimistic_trials)
            opt_min = min(optimistic_trials)
            opt_max = max(optimistic_trials)

            base_avg = sum(baseline_trials) / len(baseline_trials)
            base_min = min(baseline_trials)
            base_max = max(baseline_trials)

            metrics = {
                "optimistic_latency_ms": {
                    "avg": round(opt_avg, 2),
                    "min": round(opt_min, 2),
                    "max": round(opt_max, 2),
                    "under_16ms": opt_max < 16.0,
                    "trials": [round(x, 2) for x in optimistic_trials]
                },
                "baseline_roundtrip_ms": {
                    "avg": round(base_avg, 2),
                    "min": round(base_min, 2),
                    "max": round(base_max, 2),
                    "trials": [round(x, 2) for x in baseline_trials]
                },
                "speedup_factor": round(base_avg / max(opt_avg, 0.01), 1)
            }
    finally:
        server.should_exit = True
        thread.join(timeout=2.0)

    return metrics


if __name__ == "__main__":
    result = run_benchmark()
    print("=== LATENCY BENCHMARK RESULT ===")
    print(json.dumps(result, indent=2))
