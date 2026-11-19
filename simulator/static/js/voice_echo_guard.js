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
  const BARGE_IN_MIN_RMS = 0.038;
  const BARGE_IN_ECHO_RATIO = 1.85;
  const BARGE_IN_FLOOR_RATIO = 3.0;
  const BARGE_IN_GAP_TOLERANCE_MS = 140;
  const ECHO_WARMUP_MS = 340;
  const ECHO_WARMUP_NEAR_RMS = 0.095;
  const ECHO_CORR_SUPPRESS_RHO = 0.76;
  const ECHO_CORR_LOCK_RHO = 0.72;
  const ECHO_ENV_HISTORY_LEN = 12;
  const ECHO_LEVEL_DECAY = 0.80;
  const ECHO_LEVEL_ATTACK = 0.12;
  const AMBIENT_FLOOR_ALPHA = 0.08;
  const AMBIENT_FLOOR_MAX = 0.012;
  const ECHO_LEVEL_MIN = 0.004;
  const ECHO_LEVEL_MAX = 0.075;
  const REF_TARGET_SR = 2000;
  const MAX_REF_SAMPLES_2K = 24000; // 12 seconds @ 2kHz
  const MAX_SEARCH_LAG_MS = 300;
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

  function computeSpectralMagnitudeCorrelation(mic2k, ref2k, refStart, n) {
    if (!mic2k || !ref2k || n < 16 || refStart < 0 || refStart + n > ref2k.length) {
      return 0;
    }
    const maxBin = Math.min(17, Math.floor(n / 2));
    if (maxBin <= 2) return 0;
    const twoPiOverN = (2.0 * Math.PI) / n;
    let mEnergy = 0;
    let rEnergy = 0;
    let dot = 0;
    for (let k = 2; k < maxBin; k++) {
      let mRe = 0;
      let mIm = 0;
      let rRe = 0;
      let rIm = 0;
      for (let i = 0; i < n; i++) {
        const w = 0.5 * (1.0 - Math.cos(twoPiOverN * i));
        const ang = twoPiOverN * k * i;
        const ca = Math.cos(ang);
        const sa = Math.sin(ang);
        const mv = mic2k[i] * w;
        const rv = ref2k[refStart + i] * w;
        mRe += mv * ca;
        mIm -= mv * sa;
        rRe += rv * ca;
        rIm -= rv * sa;
      }
      const mMag = Math.sqrt(mRe * mRe + mIm * mIm);
      const rMag = Math.sqrt(rRe * rRe + rIm * rIm);
      mEnergy += mMag * mMag;
      rEnergy += rMag * rMag;
      dot += mMag * rMag;
    }
    if (mEnergy < 1e-12 || rEnergy < 1e-12) return 0;
    return Math.min(1.0, dot / Math.sqrt(mEnergy * rEnergy));
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
    let lockHits = 0;
    let echoGainEst = 0;
    let envHistMic = [];
    let envHistRef = [];
    let lastRho = 0;
    let lastAbsRho = 0;
    let lastSpecRho = 0;
    let lastEnvRho = 0;

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
      lockHits = 0;
      echoGainEst = 0;
      envHistMic = [];
      envHistRef = [];
      lastRho = 0;
      lastAbsRho = 0;
      lastSpecRho = 0;
      lastEnvRho = 0;
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
        return { rho: 0, absRho: 0, specRho: 0, envRho: 0, refRms: 0 };
      }

      const curIdx = Math.round(((now - ref2kOriginMs) * REF_TARGET_SR) / 1000.0);
      const maxLagSamples = Math.round((MAX_SEARCH_LAG_MS * REF_TARGET_SR) / 1000.0);
      let bestRho = 0;
      let bestAbsRho = 0;
      let bestLag = 0;
      let bestSt = -1;
      let bestRefRms = 0;
      let evaluatedAny = false;

      function scoreLag(lag) {
        const st = curIdx - lag;
        if (st < 0 || st + n > ref2kSamples.length) return;
        evaluatedAny = true;
        let refE = 0;
        let dot = 0;
        let absDot = 0;
        for (let j = 0; j < n; j++) {
          const r = ref2kSamples[st + j];
          const m = mic2k[j];
          refE += r * r;
          dot += m * r;
          absDot += Math.abs(m) * Math.abs(r);
        }
        if (refE < 1e-9) return;
        const denom = Math.sqrt(micE * refE);
        const rho = Math.abs(dot) / denom;
        if (rho > bestRho) {
          bestRho = rho;
          bestAbsRho = absDot / denom;
          bestLag = lag;
          bestSt = st;
          bestRefRms = Math.sqrt(refE / n);
        }
      }

      if (lockedLag2k !== null) {
        const lo = Math.max(0, lockedLag2k - 14);
        const hi = Math.min(maxLagSamples, lockedLag2k + 14);
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

      let specRho = bestSt >= 0
        ? computeSpectralMagnitudeCorrelation(mic2k, ref2kSamples, bestSt, n)
        : 0;

      if (bestRho >= ECHO_CORR_LOCK_RHO) {
        lockedLag2k = lockedLag2k === null
          ? bestLag
          : Math.round(lockedLag2k * 0.6 + bestLag * 0.4);
        lockHits = Math.min(20, lockHits + 1);
      }

      const mic2kRms = Math.sqrt(micE / n);
      let refEnvRms = bestRefRms;
      if (lockedLag2k !== null) {
        const lst = curIdx - lockedLag2k;
        if (lst >= 0 && lst + n <= ref2kSamples.length) {
          let lRefE = 0;
          let lAbsDot = 0;
          for (let j = 0; j < n; j++) {
            const r = ref2kSamples[lst + j];
            lRefE += r * r;
            lAbsDot += Math.abs(mic2k[j]) * Math.abs(r);
          }
          refEnvRms = Math.sqrt(lRefE / n);
          if (lRefE >= 1e-9) {
            const lAbsRho = lAbsDot / Math.sqrt(micE * lRefE);
            if (lAbsRho > bestAbsRho) bestAbsRho = lAbsRho;
          }
          const lSpecRho = computeSpectralMagnitudeCorrelation(mic2k, ref2kSamples, lst, n);
          if (lSpecRho > specRho) specRho = lSpecRho;
        }
      }

      envHistMic.push(mic2kRms);
      envHistRef.push(refEnvRms);
      if (envHistMic.length > ECHO_ENV_HISTORY_LEN) {
        envHistMic.shift();
        envHistRef.shift();
      }

      let envRho = 0;
      if (envHistMic.length >= 6) {
        const len = envHistMic.length;
        let meanM = 0;
        let meanR = 0;
        for (let i = 0; i < len; i++) {
          meanM += envHistMic[i];
          meanR += envHistRef[i];
        }
        meanM /= len;
        meanR /= len;
        let varM = 0;
        let varR = 0;
        let cov = 0;
        for (let i = 0; i < len; i++) {
          const dm = envHistMic[i] - meanM;
          const dr = envHistRef[i] - meanR;
          varM += dm * dm;
          varR += dr * dr;
          cov += dm * dr;
        }
        if (varM > 1e-9 && varR > 1e-9) {
          envRho = Math.max(0, cov / Math.sqrt(varM * varR));
        }
      }

      return {
        rho: Math.min(1.0, bestRho),
        absRho: Math.min(1.0, bestAbsRho),
        specRho: Math.min(1.0, specRho),
        envRho: Math.min(1.0, envRho),
        refRms: refEnvRms,
      };
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
            const absRho = corrRes.absRho;
            const specRho = corrRes.specRho;
            const envRho = corrRes.envRho;
            const refRms = corrRes.refRms;
            lastRho = rho;
            lastAbsRho = absRho;
            lastSpecRho = specRho;
            lastEnvRho = envRho;

            if (rho >= ECHO_CORR_LOCK_RHO && refRms > 0.02 && rms > 0.01) {
              const g = rms / refRms;
              echoGainEst = echoGainEst <= 0
                ? Math.min(3.5, g)
                : Math.min(3.5, echoGainEst * 0.85 + g * 0.15);
            }

            const expectedEcho = (lockedLag2k !== null && lockHits >= 2 && echoGainEst > 0 && refRms > 0.015)
              ? echoGainEst * refRms
              : 0;
            const withinExpectedEcho = expectedEcho > 0 && rms <= expectedEcho * 1.65;

            const echoMatched =
              rho >= ECHO_CORR_SUPPRESS_RHO ||
              (rho >= 0.54 && specRho >= 0.91) ||
              (rho >= 0.62 && absRho >= 0.83 && specRho >= 0.84) ||
              (withinExpectedEcho && rho >= 0.54 && absRho >= 0.78) ||
              (withinExpectedEcho && rho >= 0.54 && specRho >= 0.80 && envRho >= 0.25) ||
              (withinExpectedEcho && absRho >= 0.82 && specRho >= 0.84 && envRho >= 0.65 && rho >= 0.42) ||
              (lockedLag2k !== null && lockHits >= 2 && specRho >= 0.90 && envRho >= 0.75 && absRho >= 0.82 && rho >= 0.45);

            const effRho = Math.max(
              rho,
              (withinExpectedEcho && rho >= 0.50 && absRho >= 0.78) ? absRho * 0.86 : 0
            );
            nearRms = rms * Math.sqrt(Math.max(0, 1.0 - Math.min(1.0, effRho) * Math.min(1.0, effRho)));
            const inWarmup = playbackStartMs > 0 && (now - playbackStartMs) < warmupMs;
            if (playbackStartMs > 0 && now < playbackStartMs) {
              isNearEnd = false;
            } else if (inWarmup) {
              isNearEnd = speechLikeVad && !echoMatched && rho < 0.62 && nearRms >= Math.max(bargeInMinRms * 2.0, ECHO_WARMUP_NEAR_RMS);
            } else {
              const adaptiveNearMin = Math.max(bargeInMinRms, Math.min(0.085, expectedEcho * 0.35));
              const floorThr = Math.max(bargeInMinRms, ambientNoiseFloorRms * bargeInFloorRatio);
              isNearEnd = speechLikeVad && !echoMatched && nearRms >= adaptiveNearMin && rms >= floorThr;
            }
          }
        }

        if (!usedRefCorr) {
          const inWarmupNoCorr = playbackStartMs > 0 && (now - playbackStartMs) < warmupMs;
          if (ref2kSamples.length >= 16 && (now < playbackStartMs || inWarmupNoCorr)) {
            isNearEnd = false;
          } else {
            isNearEnd = speechLikeVad && rms >= threshold;
            if (!isNearEnd && pbState.isPlaying && bargeInAccumMs === 0 && rms < threshold * 0.85) {
              const alpha = rms > estimatedEchoRms ? ECHO_LEVEL_ATTACK : (1.0 - ECHO_LEVEL_DECAY);
              estimatedEchoRms = Math.min(
                ECHO_LEVEL_MAX,
                Math.max(ECHO_LEVEL_MIN, estimatedEchoRms * (1.0 - alpha) + rms * alpha)
              );
            }
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
        lockHits: lockHits,
        echoGainEst: echoGainEst,
        lastRho: lastRho,
        lastAbsRho: lastAbsRho,
        lastSpecRho: lastSpecRho,
        lastEnvRho: lastEnvRho,
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
