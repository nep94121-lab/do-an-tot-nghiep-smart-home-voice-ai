/**
 * Smart Home Voice Echo Guard (Client-Side Reference-Aware Echo Suppression + Barge-In Gate)
 *
 * Pure state machine + DSP helpers shared across Desktop (/), Mobile (/app),
 * Guest pages, and Node.js automated loopback/barge-in tests.
 *
 * Uses 2kHz downsampled normalized waveform cross-correlation (orthogonal projection)
 * when TTS playback reference samples are supplied so echo suppression remains
 * invariant even if the browser ignores autoGainControl: false and boosts echo.
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
  const BARGE_IN_MIN_RMS = 0.045;
  const BARGE_IN_ECHO_RATIO = 1.85;
  const BARGE_IN_FLOOR_RATIO = 3.0;
  const BARGE_IN_GAP_TOLERANCE_MS = 100;
  const ECHO_WARMUP_MS = 340;
  const ECHO_WARMUP_NEAR_RMS = 0.095;
  const ECHO_CORR_SUPPRESS_RHO = 0.78;
  const ECHO_CORR_LOCK_RHO = 0.76;
  const ECHO_LEVEL_DECAY = 0.80;
  const ECHO_LEVEL_ATTACK = 0.12;
  const AMBIENT_FLOOR_ALPHA = 0.08;
  const AMBIENT_FLOOR_MAX = 0.012;
  const ECHO_LEVEL_MIN = 0.004;
  const ECHO_LEVEL_MAX = 0.075;
  const REF_TARGET_SR = 2000;
  const MAX_REF_SAMPLES_2K = 24000; // 12 seconds @ 2kHz
  const MAX_SEARCH_LAG_MS = 220;
  const SUBFRAME_MS = 20;

  const STANDARD_MIC_AUDIO_CONSTRAINTS = Object.freeze({
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: false,
  });

  function getStandardMicConstraints(extra) {
    const audio = Object.assign({}, STANDARD_MIC_AUDIO_CONSTRAINTS, extra || {});
    audio.echoCancellation = true;
    audio.noiseSuppression = true;
    audio.autoGainControl = false;
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

  function computeZeroCrossingRate(samples, isInt16) {
    if (!samples || samples.length < 2) return 0.1;
    let crossings = 0;
    let prev = isInt16 ? samples[0] / 32768.0 : samples[0];
    for (let i = 1; i < samples.length; i++) {
      const cur = isInt16 ? samples[i] / 32768.0 : samples[i];
      if ((prev >= 0 && cur < 0) || (prev < 0 && cur >= 0)) {
        crossings += 1;
      }
      prev = cur;
    }
    return crossings / (samples.length - 1);
  }

  function downsampleTo2k(samples, sampleRate, isInt16) {
    if (!samples || !samples.length) return null;
    const sr = Number(sampleRate) || 16000;
    if (sr <= 0) return null;
    const ratio = sr / REF_TARGET_SR;
    const outLen = Math.floor(samples.length / ratio);
    if (outLen <= 0) return null;
    const out = new Float32Array(outLen);
    const invScale = isInt16 ? 1.0 / 32768.0 : 1.0;
    for (let i = 0; i < outLen; i++) {
      const start = Math.floor(i * ratio);
      const end = Math.min(samples.length, Math.max(start + 1, Math.floor((i + 1) * ratio)));
      let sum = 0;
      for (let j = start; j < end; j++) {
        sum += samples[j] * invScale;
      }
      out[i] = sum / (end - start);
    }
    return out;
  }

  function createVoiceEchoGuard(options) {
    const opts = options || {};
    const tailHoldMs = Number.isFinite(opts.tailHoldMs) ? Number(opts.tailHoldMs) : ECHO_TAIL_HOLD_MS;
    const bargeInHoldMs = Number.isFinite(opts.bargeInHoldMs) ? Number(opts.bargeInHoldMs) : BARGE_IN_HOLD_MS;
    const bargeInMinRms = Number.isFinite(opts.bargeInMinRms) ? Number(opts.bargeInMinRms) : BARGE_IN_MIN_RMS;
    const bargeInEchoRatio = Number.isFinite(opts.bargeInEchoRatio) ? Number(opts.bargeInEchoRatio) : BARGE_IN_ECHO_RATIO;
    const bargeInFloorRatio = Number.isFinite(opts.bargeInFloorRatio) ? Number(opts.bargeInFloorRatio) : BARGE_IN_FLOOR_RATIO;
    const gapToleranceMs = Number.isFinite(opts.gapToleranceMs) ? Number(opts.gapToleranceMs) : BARGE_IN_GAP_TOLERANCE_MS;
    const warmupMs = Number.isFinite(opts.warmupMs) ? Number(opts.warmupMs) : ECHO_WARMUP_MS;
    const onBargeIn = typeof opts.onBargeIn === "function" ? opts.onBargeIn : null;

    let activeSourcesCount = 0;
    let playbackStartMs = 0;
    let playbackEndMs = 0;
    let lastPlaybackEndedAtMs = 0;
    let estimatedEchoRms = ECHO_LEVEL_MIN;
    let ambientNoiseFloorRms = 0.002;
    let bargeInAccumMs = 0;
    let bargeInMissMs = 0;
    let bargeInActive = false;

    let ref2kSamples = [];
    let ref2kOriginMs = 0;
    let lockedLag2k = null;
    let lastRho = 0;

    function resolveNow(nowMs) {
      if (Number.isFinite(nowMs)) return Number(nowMs);
      if (typeof performance !== "undefined" && typeof performance.now === "function") {
        return performance.now();
      }
      return Date.now();
    }

    function resetReferenceBuffer(originMs) {
      ref2kSamples = [];
      ref2kOriginMs = originMs;
      lockedLag2k = null;
      lastRho = 0;
    }

    function appendReferenceAudio(refAudio, scheduledStartMs) {
      if (!refAudio) return;
      const samples = refAudio.samples || refAudio.pcm16 || null;
      if (!samples || !samples.length) return;
      const isInt16 = samples instanceof Int16Array || Boolean(refAudio.isInt16);
      const sr = Number(refAudio.sampleRate) || 24000;
      const ds = downsampleTo2k(samples, sr, isInt16);
      if (!ds || !ds.length) return;

      if (ref2kSamples.length === 0) {
        ref2kOriginMs = scheduledStartMs;
      } else {
        const expectedStartIdx = Math.round(((scheduledStartMs - ref2kOriginMs) * REF_TARGET_SR) / 1000.0);
        if (expectedStartIdx > ref2kSamples.length && expectedStartIdx - ref2kSamples.length <= 2000) {
          const pad = expectedStartIdx - ref2kSamples.length;
          for (let p = 0; p < pad; p++) ref2kSamples.push(0);
        } else if (expectedStartIdx > ref2kSamples.length + 2000) {
          resetReferenceBuffer(scheduledStartMs);
        }
      }

      for (let i = 0; i < ds.length; i++) {
        ref2kSamples.push(ds[i]);
      }

      if (ref2kSamples.length > MAX_REF_SAMPLES_2K) {
        const drop = ref2kSamples.length - MAX_REF_SAMPLES_2K;
        ref2kSamples = ref2kSamples.slice(drop);
        ref2kOriginMs += (drop * 1000.0) / REF_TARGET_SR;
      }
    }

    function notePlaybackQueued(durationMs, nowMs, refAudio) {
      const now = resolveNow(nowMs);
      const dur = Math.max(0, Number(durationMs) || 0);
      const wasPlaying = playbackEndMs > now;
      const startOffsetMs = refAudio && Number.isFinite(refAudio.startOffsetMs)
        ? Math.max(0, Number(refAudio.startOffsetMs))
        : 0;
      const base = wasPlaying ? playbackEndMs : now + startOffsetMs;
      if (!wasPlaying) {
        playbackStartMs = base;
        resetReferenceBuffer(base);
      }
      bargeInActive = false;
      bargeInAccumMs = 0;
      bargeInMissMs = 0;
      activeSourcesCount += 1;
      playbackEndMs = base + dur;
      lastPlaybackEndedAtMs = playbackEndMs;
      if (refAudio) {
        appendReferenceAudio(refAudio, base);
      }
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
      playbackStartMs = 0;
      playbackEndMs = 0;
      lastPlaybackEndedAtMs = 0;
      bargeInAccumMs = 0;
      bargeInMissMs = 0;
      bargeInActive = false;
      resetReferenceBuffer(0);
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

    function computeWaveformCorrelation(mic2k, now) {
      if (!ref2kSamples.length || !mic2k || mic2k.length < 8) {
        return null;
      }
      const n = mic2k.length;
      let micE = 0;
      for (let j = 0; j < n; j++) {
        micE += mic2k[j] * mic2k[j];
      }
      if (micE < 1e-9) {
        return { rho: 0, refRms: 0 };
      }

      const curIdx = Math.round(((now - ref2kOriginMs) * REF_TARGET_SR) / 1000.0);
      const maxLagSamples = Math.round((MAX_SEARCH_LAG_MS * REF_TARGET_SR) / 1000.0);
      let bestRho = 0;
      let bestLag = 0;
      let bestRefRms = 0;
      let evaluatedAny = false;

      function scoreLag(lag) {
        const st = curIdx - lag;
        if (st < 0 || st + n > ref2kSamples.length) return;
        evaluatedAny = true;
        let refE = 0;
        let dot = 0;
        for (let j = 0; j < n; j++) {
          const r = ref2kSamples[st + j];
          refE += r * r;
          dot += mic2k[j] * r;
        }
        if (refE < 1e-9) return;
        const rho = Math.abs(dot) / Math.sqrt(micE * refE);
        if (rho > bestRho) {
          bestRho = rho;
          bestLag = lag;
          bestRefRms = Math.sqrt(refE / n);
        }
      }

      if (lockedLag2k !== null) {
        const lo = Math.max(0, lockedLag2k - 10);
        const hi = Math.min(maxLagSamples, lockedLag2k + 10);
        for (let lag = lo; lag <= hi; lag++) {
          scoreLag(lag);
        }
      }
      if (lockedLag2k === null || bestRho < 0.55) {
        for (let lag = 0; lag <= maxLagSamples; lag += 2) {
          scoreLag(lag);
        }
        if (bestRho > 0.25) {
          scoreLag(Math.max(0, bestLag - 1));
          scoreLag(Math.min(maxLagSamples, bestLag + 1));
        }
      }

      if (!evaluatedAny) {
        return null;
      }
      if (bestRho >= ECHO_CORR_LOCK_RHO) {
        lockedLag2k = bestLag;
      }
      return { rho: Math.min(1.0, bestRho), refRms: bestRefRms };
    }

    function evaluateSingleSubframe(rms, frameDurationMs, now, subSamples, sampleRate, isInt16) {
      const pbState = getPlaybackState(now);
      const threshold = computeBargeInThreshold();

      if (pbState.blocked && !bargeInActive) {
        let isNearEnd = false;
        let usedRefCorr = false;
        let nearRms = rms;
        let rho = 0;

        const speechLikeVad = (!subSamples || subSamples.length < 16)
          ? true
          : (function () {
              const zcr = computeZeroCrossingRate(subSamples, isInt16);
              return zcr >= 0.006 && zcr <= 0.48;
            })();

        if (subSamples && subSamples.length >= 32 && ref2kSamples.length >= 16) {
          const mic2k = downsampleTo2k(subSamples, sampleRate, isInt16);
          const corrRes = computeWaveformCorrelation(mic2k, now);
          if (corrRes !== null) {
            usedRefCorr = true;
            rho = corrRes.rho;
            lastRho = rho;
            // Orthogonal projection residual: invariant to browser AGC gain scaling
            nearRms = rms * Math.sqrt(Math.max(0, 1.0 - rho * rho));
            const inWarmup = playbackStartMs > 0 && (now - playbackStartMs) < warmupMs;
            if (inWarmup) {
              isNearEnd = speechLikeVad && rho < 0.65 && nearRms >= Math.max(bargeInMinRms * 2.0, ECHO_WARMUP_NEAR_RMS);
            } else {
              const floorThr = Math.max(bargeInMinRms, ambientNoiseFloorRms * bargeInFloorRatio);
              isNearEnd = speechLikeVad && rho < ECHO_CORR_SUPPRESS_RHO && nearRms >= bargeInMinRms && rms >= floorThr;
            }
          }
        }

        if (!usedRefCorr) {
          isNearEnd = speechLikeVad && rms >= threshold;
          if (!isNearEnd && pbState.isPlaying && bargeInAccumMs === 0 && rms < threshold * 0.85) {
            const alpha = rms > estimatedEchoRms ? ECHO_LEVEL_ATTACK : (1.0 - ECHO_LEVEL_DECAY);
            estimatedEchoRms = Math.min(
              ECHO_LEVEL_MAX,
              Math.max(ECHO_LEVEL_MIN, estimatedEchoRms * (1.0 - alpha) + rms * alpha)
            );
          }
        }

        if (isNearEnd) {
          bargeInAccumMs += frameDurationMs;
          bargeInMissMs = 0;
          if (bargeInAccumMs >= bargeInHoldMs) {
            bargeInActive = true;
            activeSourcesCount = 0;
            playbackStartMs = 0;
            playbackEndMs = 0;
            lastPlaybackEndedAtMs = 0;
            bargeInAccumMs = 0;
            bargeInMissMs = 0;
            resetReferenceBuffer(0);
            if (onBargeIn) {
              try {
                onBargeIn({ rms: rms, nearRms: nearRms, rho: rho, threshold: threshold, nowMs: now });
              } catch (_) {}
            }
            return {
              allowSend: true,
              bargeInTriggered: true,
              phase: "BARGE_IN",
              threshold: threshold,
              estimatedEchoRms: estimatedEchoRms,
              nearRms: nearRms,
              echoCorrelation: rho,
            };
          }
          return {
            allowSend: false,
            bargeInTriggered: false,
            phase: pbState.phase,
            threshold: threshold,
            estimatedEchoRms: estimatedEchoRms,
            bargeInAccumMs: bargeInAccumMs,
            nearRms: nearRms,
            echoCorrelation: rho,
          };
        }

        if (bargeInAccumMs > 0) {
          bargeInMissMs += frameDurationMs;
          if (bargeInMissMs > gapToleranceMs) {
            bargeInAccumMs = 0;
            bargeInMissMs = 0;
          }
        }

        return {
          allowSend: false,
          bargeInTriggered: false,
          phase: pbState.phase,
          threshold: threshold,
          estimatedEchoRms: estimatedEchoRms,
          bargeInAccumMs: bargeInAccumMs,
          nearRms: nearRms,
          echoCorrelation: rho,
        };
      }

      if (!pbState.blocked) {
        bargeInActive = false;
        bargeInAccumMs = 0;
        bargeInMissMs = 0;
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
        nearRms: rms,
        echoCorrelation: 0,
      };
    }

    function evaluateMicFrame(frame) {
      const f = frame || {};
      const samples = f.samples || f.pcm16 || null;
      const isInt16 = samples ? (samples instanceof Int16Array || Boolean(f.isInt16)) : false;
      const sampleRate = Number(f.sampleRate) || 16000;
      const frameDurationMs = Math.max(1, Number(f.frameDurationMs) || (samples ? (samples.length / sampleRate) * 1000.0 : 20));
      const now = resolveNow(f.nowMs);

      // Slice large WebAudio ScriptProcessor callbacks (>30ms) into 20ms sub-frames
      if (samples && samples.length > 0 && frameDurationMs > 30) {
        const subLen = Math.max(1, Math.round((sampleRate * SUBFRAME_MS) / 1000.0));
        const numSubs = Math.max(1, Math.floor(samples.length / subLen));
        let lastRes = null;
        for (let k = 0; k < numSubs; k++) {
          const st = k * subLen;
          const en = k === numSubs - 1 ? samples.length : (k + 1) * subLen;
          const sub = samples.subarray ? samples.subarray(st, en) : samples.slice(st, en);
          const subDur = ((en - st) / sampleRate) * 1000.0;
          const subRms = isInt16 ? computePcm16Rms(sub) : computeFloat32Rms(sub);
          const subNow = now - frameDurationMs + (k + 1) * SUBFRAME_MS;
          lastRes = evaluateSingleSubframe(subRms, subDur, subNow, sub, sampleRate, isInt16);
          if (lastRes.bargeInTriggered) {
            return lastRes;
          }
        }
        return lastRes;
      }

      const rms = Number.isFinite(f.rms)
        ? Math.max(0, Number(f.rms))
        : (samples ? (isInt16 ? computePcm16Rms(samples) : computeFloat32Rms(samples)) : 0);
      return evaluateSingleSubframe(rms, frameDurationMs, now, samples, sampleRate, isInt16);
    }

    function getDebugSnapshot(nowMs) {
      const pb = getPlaybackState(nowMs);
      return {
        phase: pb.phase,
        blocked: pb.blocked,
        activeSourcesCount: activeSourcesCount,
        playbackStartMs: playbackStartMs,
        playbackEndMs: playbackEndMs,
        lastPlaybackEndedAtMs: lastPlaybackEndedAtMs,
        estimatedEchoRms: estimatedEchoRms,
        ambientNoiseFloorRms: ambientNoiseFloorRms,
        bargeInAccumMs: bargeInAccumMs,
        bargeInMissMs: bargeInMissMs,
        bargeInActive: bargeInActive,
        bargeInThreshold: computeBargeInThreshold(),
        lockedLag2k: lockedLag2k,
        lastRho: lastRho,
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
    BARGE_IN_GAP_TOLERANCE_MS: BARGE_IN_GAP_TOLERANCE_MS,
    ECHO_WARMUP_MS: ECHO_WARMUP_MS,
    STANDARD_MIC_AUDIO_CONSTRAINTS: STANDARD_MIC_AUDIO_CONSTRAINTS,
    getStandardMicConstraints: getStandardMicConstraints,
    computeFloat32Rms: computeFloat32Rms,
    computePcm16Rms: computePcm16Rms,
    createVoiceEchoGuard: createVoiceEchoGuard,
  };
});
