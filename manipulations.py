"""Audio manipulation pipeline for the game database builder.

Codec compression : MP3 via ffmpeg
Noise addition    : AWGN, ISD ambient noise at target SNR
Cheapfakes        : tempo change, pitch shift (librosa)
Resampling        : down/up-sample round-trip

References:
  SAFE challenge: Kirill et al. (2025). IH&MMSec.
  ISD: Mitchell et al. (2024). Zenodo. https://doi.org/10.5281/zenodo.10672568
"""
import logging
import os
import subprocess
from math import gcd
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

logger = logging.getLogger(__name__)
_FFMPEG = os.environ.get("FFMPEG_BIN", r"C:/Users/lerscoi/ffmpeg/ffmpeg-9.0.1-essentials_build/bin/ffmpeg.exe")

def _resample(audio, src_sr, tgt_sr):
    if src_sr == tgt_sr:
        return audio.astype(np.float32)
    g = gcd(int(src_sr), int(tgt_sr))
    return resample_poly(audio.astype(np.float64), tgt_sr // g, src_sr // g).astype(np.float32)

def _fix_length(audio, n):
    if len(audio) > n:
        return audio[:n]
    if len(audio) < n:
        return np.pad(audio, (0, n - len(audio)))
    return audio

def _mix_at_snr(speech, noise, snr_db):
    x, n = speech.astype(np.float64), noise.astype(np.float64)
    rms_x = np.sqrt(np.mean(x ** 2))
    rms_n = np.sqrt(np.mean(n ** 2)) + 1e-9
    return np.clip(x + n * (rms_x / (rms_n * 10.0 ** (snr_db / 20.0))), -1.0, 1.0).astype(np.float32)

def _load_noise_segment(path, n_samples, tgt_sr, offset_index=0):
    noise, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if noise.ndim > 1:
        noise = noise.mean(axis=1)
    noise = _resample(noise, sr, tgt_sr)
    if len(noise) < n_samples:
        noise = np.tile(noise, -(-n_samples // len(noise)))
    start = (offset_index * n_samples) % max(1, len(noise) - n_samples)
    return noise[start:start + n_samples].astype(np.float32)

def mp3(audio, sr, **_):
    import shutil
    ffmpeg = shutil.which(_FFMPEG)
    if ffmpeg is None:
        raise RuntimeError(f"ffmpeg not found on PATH (FFMPEG_BIN={_FFMPEG!r}). Install ffmpeg or set FFMPEG_BIN.")
    tmp = Path(__file__).parent / "codec_tmp"
    tmp.mkdir(exist_ok=True)
    pid = os.getpid()
    src, mid, dst = tmp / f"in_{pid}.wav", tmp / f"mid_{pid}.mp3", tmp / f"out_{pid}.wav"
    sf.write(str(src), audio, sr)
    try:
        for cmd, label in [
            ([_FFMPEG, "-y", "-v", "error", "-i", str(src), "-c:a", "libmp3lame", "-b:a", "16k", str(mid)], "encode"),
            ([_FFMPEG, "-y", "-v", "error", "-i", str(mid), "-ar", str(sr), str(dst)], "decode"),
        ]:
            r = subprocess.run(cmd, capture_output=True)
            if r.returncode != 0:
                raise RuntimeError(f"ffmpeg {label} failed: {r.stderr.decode(errors='replace')[:500]}")
        out, out_sr = sf.read(str(dst), dtype="float32", always_2d=False)
        if out.ndim > 1:
            out = out.mean(axis=1)
        return _fix_length(_resample(out, out_sr, sr), len(audio))
    finally:
        for p in (src, mid, dst):
            p.unlink(missing_ok=True)

def gaussian_noise(audio, sr, snr_db=20.0, seed=42, **_):
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    if rms < 1e-4:
        return audio.astype(np.float32)
    noise = np.random.default_rng(int(seed)).standard_normal(len(audio))
    noise /= float(np.sqrt(np.mean(noise ** 2))) + 1e-9
    return np.clip(audio.astype(np.float64) + noise * (rms / 10.0 ** (snr_db / 20.0)), -1.0, 1.0).astype(np.float32)

def soundscape_mix(audio, sr, snr_db=20.0, noise_index=0, soundscape_dir=None, **_):
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    if rms < 1e-4:
        return audio.astype(np.float32)
    d = Path(soundscape_dir)
    noise_files = sorted(d.rglob("*.wav"))
    if not noise_files:
        raise RuntimeError(f"No WAV files in soundscape dir: {d}")
    noise = _load_noise_segment(noise_files[int(noise_index) % len(noise_files)], len(audio), sr, int(noise_index))
    return _mix_at_snr(audio, noise, snr_db)

def time_stretch(audio, sr, rate=1.1, **_):
    return _fix_length(librosa.effects.time_stretch(audio.astype(np.float32), rate=float(rate)), len(audio))

def pitch_shift(audio, sr, n_steps=2.0, **_):
    return librosa.effects.pitch_shift(audio.astype(np.float32), sr=sr, n_steps=float(n_steps))

def resample_down(audio, sr, target_sr=8000, **_):
    tgt = max(4000, int(target_sr))
    return _fix_length(_resample(_resample(audio, sr, tgt), tgt, sr), len(audio))

def resample_up(audio, sr, target_sr=48000, **_):
    tgt = int(target_sr)
    return _fix_length(_resample(_resample(audio, sr, tgt), tgt, sr), len(audio))

MANIPULATIONS = {
    "MP3":            (mp3,            {}),
    "Gaussian Noise": (gaussian_noise, {"snr_db": 20.0}),
    "Soundscape Mix": (soundscape_mix, {"snr_db": 20.0}),
    "Time Stretch":   (time_stretch,   {"rate": 1.1}),
    "Pitch Shift":    (pitch_shift,    {"n_steps": 2.0}),
    "Resample Down":  (resample_down,  {"target_sr": 8000}),
    "Resample Up":    (resample_up,    {"target_sr": 48000}),
}

PARAM_RANGES = {
    "Gaussian Noise": {"snr_db":    (10.0, 30.0, float)},
    "Soundscape Mix": {"snr_db":    (10.0, 30.0, float)},
    "Time Stretch":   {"rate":      (0.8,  1.25,  float)},
    "Pitch Shift":    {"n_steps":   (1,    12,    int)},
    "Resample Down":  {"target_sr": (4000, 16000, int)},
    "Resample Up":    {"target_sr": (24000, 48000, int)},
}