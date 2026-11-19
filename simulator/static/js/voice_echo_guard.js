/**
 * Smart Home Voice Echo Guard (Client-Side Half-Duplex + Barge-In Gate)
 *
 * Pure state machine + DSP helpers shared across Desktop (/), Mobile (/app),
 * Guest pages, and Node.js automated loopback/barge-in tests.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.SmartHomeEchoGuard = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const ECHO_TAIL_HOLD_MS = 400;
  const BARGE_IN_HOLD_MS = 250;
  const BARGE_IN_MIN_RMS = 0.065;
  const BARGE_IN_ECHO_RATIO = 2.4;
  const BARGE_IN_FLOOR_RATIO = 3.2;
  const ECHO_LEVEL_DECAY = 0.88;
  const ECHO_LEVEL_ATTACK = 0.35;
  const AMBIENT_FLOOR_ALPHA = 0.08;
  const AMBIENT_FLOOR_MAX = 0.012;
  const ECHO_LEVEL_MIN = 0.004;
  const ECHO_LEVEL_MAX = 0.25;

  const STANDARD_MIC_AUDIO_CONSTRAINTS = Object.freeze({
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  });

  function getStandardMicConstraints(extra) {
    const audio = Object.assign({}, STANDARD_MIC_AUDIO_CONSTRAINTS, extra || {});
    audio.echoCancellation = true;
    audio.noiseSuppression = true;
    audio.autoGainControl = true;
    return { audio: audio };
  }

  function computeFloat32Rms(samples) {
    if (!samples || !samples.length) return 0;
    let sumSq = 0;
    for (let i = 0; i < samples.length; i++) {
      const s = samples[i];
      sumSq += s * s;
    }
    return Math.sqrt(sumSq / samples.length);
  }

  function computePcm16Rms(int16Samples) {
    if (!int16Samples || !int16Samples.length) return 0;
    let sumSq = 0;
    for (let i = 0; i < int16Samples.length; i++) {
      const s = int16Samples[i] / 32768.0;
      sumSq += s * s;
    }
    return Math.sqrt(sumSq / int16Samples.length);
  }

  function createVoiceEchoGuard(options) {
    const opts = options || {};
    const tailHoldMs = Number.isFinite(opts.tailHoldMs) ? Number(opts.tailHoldMs) : ECHO_TAIL_HOLD_MS;
    const bargeInHoldMs = Number.isFinite(opts.bargeInHoldMs) ? Number(opts.bargeInHoldMs) : BARGE_IN_HOLD_MS;
    const bargeInMinRms = Number.isFinite(opts.bargeInMinRms) ? Number(opts.bargeInMinRms) : BARGE_IN_MIN_RMS;
    const bargeInEchoRatio = Number.isFinite(opts.bargeInEchoRatio) ? Number(opts.bargeInEchoRatio) : BARGE_IN_ECHO_RATIO;
    const bargeInFloorRatio = Number.isFinite(opts.bargeInFloorRatio) ? Number(opts.bargeInFloorRatio) : BARGE_IN_FLOOR_RATIO;
    const onBargeIn = typeof opts.onBargeIn === "function" ? opts.onBargeIn : null;

    let activeSourcesCount = 0;
    let playbackEndMs = 0;
    let lastPlaybackEndedAtMs = 0;
    let estimatedEchoRms = ECHO_LEVEL_MIN;
    let ambientNoiseFloorRms = 0.002;
    let bargeInAccumMs = 0;
    let bargeInActive = false;

    function resolveNow(nowMs) {
      if (Number.isFinite(nowMs)) return Number(nowMs);
      if (typeof performance !== "undefined" && typeof performance.now === "function") {
        return performance.now();
      }
      return Date.now();
    }

    function notePlaybackQueued(durationMs, nowMs) {
      const now = resolveNow(nowMs);
      const dur = Math.max(0, Number(durationMs) || 0);
      bargeInActive = false;
      bargeInAccumMs = 0;
      activeSourcesCount += 1;
      const base = playbackEndMs > now ? playbackEndMs : now;
      playbackEndMs = base + dur;
      lastPlaybackEndedAtMs = playbackEndMs;
    }

    function noteSourceEnded(nowMs) {
      const now = resolveNow(nowMs);
      if (activeSourcesCount > 0) {
        activeSourcesCount -= 1;
      }
      if (activeSourcesCount === 0) {
        playbackEndMs = Math.min(playbackEndMs, now);
        lastPlaybackEndedAtMs = now;
      }
    }

    function syncAudioContextPlayback(currentTimeSec, nextPlayTimeSec, nowMs) {
      const now = resolveNow(nowMs);
      const cur = Number(currentTimeSec) || 0;
      const nxt = Number(nextPlayTimeSec) || 0;
      if (nxt > cur) {
        const remMs = (nxt - cur) * 1000.0;
        const targetEnd = now + remMs;
        if (targetEnd > playbackEndMs) {
          playbackEndMs = targetEnd;
        }
        if (playbackEndMs > lastPlaybackEndedAtMs) {
          lastPlaybackEndedAtMs = playbackEndMs;
        }
      } else if (activeSourcesCount === 0 && playbackEndMs > now) {
        playbackEndMs = now;
        lastPlaybackEndedAtMs = now;
      }
    }

    function clearPlayback(nowMs) {
      const now = resolveNow(nowMs);
      activeSourcesCount = 0;
      playbackEndMs = 0;
      lastPlaybackEndedAtMs = 0;
      bargeInAccumMs = 0;
      bargeInActive = false;
      return now;
    }

    function getPlaybackState(nowMs) {
      const now = resolveNow(nowMs);
      if (activeSourcesCount > 0 && playbackEndMs > 0 && now >= playbackEndMs) {
        activeSourcesCount = 0;
        if (lastPlaybackEndedAtMs <= 0 || lastPlaybackEndedAtMs > playbackEndMs) {
          lastPlaybackEndedAtMs = playbackEndMs;
        }
      }
      const isPlaying = playbackEndMs > now;
      if (isPlaying) {
        const remPlay = Math.max(0, playbackEndMs - now);
        return {
          blocked: true,
          isPlaying: true,
          inTail: false,
          phase: "AI_PLAYING",
          remainingMs: remPlay + tailHoldMs,
        };
      }
      if (lastPlaybackEndedAtMs > 0) {
        const elapsedSinceEnd = now - lastPlaybackEndedAtMs;
        if (elapsedSinceEnd >= 0 && elapsedSinceEnd < tailHoldMs) {
          return {
            blocked: true,
            isPlaying: false,
            inTail: true,
            phase: "ECHO_TAIL",
            remainingMs: tailHoldMs - elapsedSinceEnd,
          };
        }
      }
      return {
        blocked: false,
        isPlaying: false,
        inTail: false,
        phase: "IDLE",
        remainingMs: 0,
      };
    }

    function isPlaybackOrTailActive(nowMs) {
      return getPlaybackState(nowMs).blocked;
    }

    function computeBargeInThreshold() {
      return Math.max(
        bargeInMinRms,
        estimatedEchoRms * bargeInEchoRatio,
        ambientNoiseFloorRms * bargeInFloorRatio
      );
    }

    function evaluateMicFrame(frame) {
      const f = frame || {};
      const rms = Math.max(0, Number(f.rms) || 0);
      const frameDurationMs = Math.max(1, Number(f.frameDurationMs) || 20);
      const now = resolveNow(f.nowMs);
      const pbState = getPlaybackState(now);
      const threshold = computeBargeInThreshold();

      if (pbState.blocked && !bargeInActive) {
        if (rms >= threshold) {
          bargeInAccumMs += frameDurationMs;
          if (bargeInAccumMs >= bargeInHoldMs) {
            bargeInActive = true;
            activeSourcesCount = 0;
            playbackEndMs = 0;
            lastPlaybackEndedAtMs = 0;
            bargeInAccumMs = 0;
            if (onBargeIn) {
              try {
                onBargeIn({ rms: rms, threshold: threshold, nowMs: now });
              } catch (_) {}
            }
            return {
              allowSend: true,
              bargeInTriggered: true,
              phase: "BARGE_IN",
              threshold: threshold,
              estimatedEchoRms: estimatedEchoRms,
            };
          }
          return {
            allowSend: false,
            bargeInTriggered: false,
            phase: pbState.phase,
            threshold: threshold,
            estimatedEchoRms: estimatedEchoRms,
            bargeInAccumMs: bargeInAccumMs,
          };
        }

        bargeInAccumMs = 0;
        if (pbState.isPlaying) {
          const alpha = rms > estimatedEchoRms ? ECHO_LEVEL_ATTACK : (1.0 - ECHO_LEVEL_DECAY);
          estimatedEchoRms = Math.min(
            ECHO_LEVEL_MAX,
            Math.max(ECHO_LEVEL_MIN, estimatedEchoRms * (1.0 - alpha) + rms * alpha)
          );
        }
        return {
          allowSend: false,
          bargeInTriggered: false,
          phase: pbState.phase,
          threshold: threshold,
          estimatedEchoRms: estimatedEchoRms,
          bargeInAccumMs: 0,
        };
      }

      if (!pbState.blocked) {
        bargeInActive = false;
        bargeInAccumMs = 0;
        if (rms < Math.max(0.015, ambientNoiseFloorRms * 2.0)) {
          ambientNoiseFloorRms = Math.min(
            AMBIENT_FLOOR_MAX,
            ambientNoiseFloorRms * (1.0 - AMBIENT_FLOOR_ALPHA) + rms * AMBIENT_FLOOR_ALPHA
          );
        }
      }

      return {
        allowSend: true,
        bargeInTriggered: false,
        phase: "IDLE",
        threshold: threshold,
        estimatedEchoRms: estimatedEchoRms,
        bargeInAccumMs: 0,
      };
    }

    function getDebugSnapshot(nowMs) {
      const pb = getPlaybackState(nowMs);
      return {
        phase: pb.phase,
        blocked: pb.blocked,
        activeSourcesCount: activeSourcesCount,
        playbackEndMs: playbackEndMs,
        lastPlaybackEndedAtMs: lastPlaybackEndedAtMs,
        estimatedEchoRms: estimatedEchoRms,
        ambientNoiseFloorRms: ambientNoiseFloorRms,
        bargeInAccumMs: bargeInAccumMs,
        bargeInActive: bargeInActive,
        bargeInThreshold: computeBargeInThreshold(),
      };
    }

    return {
      notePlaybackQueued: notePlaybackQueued,
      noteSourceEnded: noteSourceEnded,
      syncAudioContextPlayback: syncAudioContextPlayback,
      clearPlayback: clearPlayback,
      getPlaybackState: getPlaybackState,
      isPlaybackOrTailActive: isPlaybackOrTailActive,
      computeBargeInThreshold: computeBargeInThreshold,
      evaluateMicFrame: evaluateMicFrame,
      getDebugSnapshot: getDebugSnapshot,
    };
  }

  return {
    ECHO_TAIL_HOLD_MS: ECHO_TAIL_HOLD_MS,
    BARGE_IN_HOLD_MS: BARGE_IN_HOLD_MS,
    BARGE_IN_MIN_RMS: BARGE_IN_MIN_RMS,
    BARGE_IN_ECHO_RATIO: BARGE_IN_ECHO_RATIO,
    BARGE_IN_FLOOR_RATIO: BARGE_IN_FLOOR_RATIO,
    STANDARD_MIC_AUDIO_CONSTRAINTS: STANDARD_MIC_AUDIO_CONSTRAINTS,
    getStandardMicConstraints: getStandardMicConstraints,
    computeFloat32Rms: computeFloat32Rms,
    computePcm16Rms: computePcm16Rms,
    createVoiceEchoGuard: createVoiceEchoGuard,
  };
});
