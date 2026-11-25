from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Optional

import httpx

from database import get_settings

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"

FALLBACK_VOICES = [
    {"voice_id": "pNInz6obpgDQGcFmaJgB", "name": "Adam (Deep Calm Narrator)", "category": "premade", "preview_url": ""},
    {"voice_id": "ErXwobaYiN019PkySvjV", "name": "Antoni (Crisp Explainer)", "category": "premade", "preview_url": ""},
    {"voice_id": "VR6AewLTigWG4xSOukaG", "name": "Arnold (Authoritative)", "category": "premade", "preview_url": ""},
    {"voice_id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh (Young Documentary)", "category": "premade", "preview_url": ""},
    {"voice_id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella (Clear & Engaging)", "category": "premade", "preview_url": ""},
]


class ElevenLabsService:
    """
    Connects to ElevenLabs `/v1/text-to-speech/{voice_id}/with-timestamps`,
    saves `narration.mp3`, and converts character alignment into exact word-level
    `timestamps.json` so Blender scene durations, keyframes, and captions lock 1:1.
    """

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.get("elevenlabs_api_key", "")

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ValueError(
                "ElevenLabs API key is not configured. Add it in Settings to synthesize voiceover."
            )
        return {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def list_voices(self) -> list[dict[str, Any]]:
        if not self.api_key:
            return FALLBACK_VOICES
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.get(
                    f"{ELEVENLABS_BASE}/voices",
                    headers={"xi-api-key": self.api_key},
                )
                r.raise_for_status()
                data = r.json()
                voices = []
                for v in data.get("voices", []):
                    voices.append(
                        {
                            "voice_id": v.get("voice_id"),
                            "name": v.get("name"),
                            "category": v.get("category", "premade"),
                            "preview_url": v.get("preview_url", ""),
                            "labels": v.get("labels", {}),
                        }
                    )
                return voices or FALLBACK_VOICES
        except Exception:
            return FALLBACK_VOICES

    async def preview_voice(self, voice_id: str, text: str) -> bytes:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": text[:280],
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.45,
                        "similarity_boost": 0.78,
                        "style": 0.2,
                        "use_speaker_boost": True,
                    },
                },
            )
            r.raise_for_status()
            return r.content

    async def generate_narration_with_timestamps(
        self,
        *,
        text: str,
        voice_id: str,
        output_audio_path: Path,
        output_timestamps_path: Path,
        model_id: str = "eleven_multilingual_v2",
    ) -> dict[str, Any]:
        output_audio_path.parent.mkdir(parents=True, exist_ok=True)
        output_timestamps_path.parent.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(
                f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}/with-timestamps",
                headers=self._headers(),
                json={
                    "text": text,
                    "model_id": model_id,
                    "voice_settings": {
                        "stability": 0.45,
                        "similarity_boost": 0.80,
                        "style": 0.15,
                        "use_speaker_boost": True,
                    },
                },
            )
            r.raise_for_status()
            payload = r.json()

        audio_b64 = payload.get("audio_base64", "")
        if not audio_b64:
            raise RuntimeError("ElevenLabs response missing audio_base64.")

        output_audio_path.write_bytes(base64.b64decode(audio_b64))

        alignment = payload.get("normalized_alignment") or payload.get("alignment") or {}
        words = _alignment_to_words(alignment)
        total_duration = words[-1]["end"] if words else max(1.0, len(text.split()) / 2.6)

        result = {
            "text": text,
            "voice_id": voice_id,
            "model_id": model_id,
            "total_duration": round(float(total_duration), 3),
            "words": words,
            "raw_alignment": alignment,
        }
        output_timestamps_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result


def _alignment_to_words(alignment: dict[str, Any]) -> list[dict[str, Any]]:
    chars: list[str] = alignment.get("characters", [])
    starts: list[float] = alignment.get("character_start_times_seconds", [])
    ends: list[float] = alignment.get("character_end_times_seconds", [])

    words: list[dict[str, Any]] = []
    buf: list[str] = []
    w_start: Optional[float] = None
    w_end: float = 0.0

    for ch, st, en in zip(chars, starts, ends):
        if ch.isspace():
            if buf:
                words.append(
                    {
                        "word": "".join(buf),
                        "start": round(float(w_start or 0.0), 3),
                        "end": round(float(w_end), 3),
                    }
                )
                buf = []
                w_start = None
        else:
            if w_start is None:
                w_start = float(st)
            w_end = float(en)
            buf.append(ch)

    if buf:
        words.append(
            {
                "word": "".join(buf),
                "start": round(float(w_start or 0.0), 3),
                "end": round(float(w_end), 3),
            }
        )
    return words


def sync_storyboard_to_timestamps(
    storyboard: dict[str, Any], timestamps_data: dict[str, Any], fps: int = 30
) -> dict[str, Any]:
    """
    Aligns each scene's start_sec, end_sec, duration_sec, start_frame, and end_frame
    1:1 to the ElevenLabs word-level timestamps!
    """
    words = timestamps_data.get("words", [])
    scenes = storyboard.get("scenes", [])
    if not words or not scenes:
        return storyboard

    word_cursor = 0
    total_words = len(words)
    total_audio_dur = float(timestamps_data.get("total_duration", words[-1]["end"]))

    for idx, scene in enumerate(scenes):
        narration = str(scene.get("narration", "")).strip()
        scene_word_count = max(1, len(narration.split()))

        start_idx = min(word_cursor, total_words - 1)
        if idx == len(scenes) - 1:
            end_idx = total_words - 1
        else:
            end_idx = min(word_cursor + scene_word_count - 1, total_words - 1)

        s_start = 0.0 if idx == 0 else float(words[start_idx]["start"])
        if idx == len(scenes) - 1:
            s_end = max(total_audio_dur, float(words[end_idx]["end"]) + 0.35)
        else:
            next_idx = min(end_idx + 1, total_words - 1)
            s_end = float(words[next_idx]["start"]) if next_idx > end_idx else float(words[end_idx]["end"])

        if s_end <= s_start + 0.4:
            s_end = s_start + max(1.0, scene_word_count * 0.35)

        scene["start_sec"] = round(s_start, 3)
        scene["end_sec"] = round(s_end, 3)
        scene["duration_sec"] = round(s_end - s_start, 3)
        scene["start_frame"] = max(1, round(s_start * fps) + 1)
        scene["end_frame"] = max(scene["start_frame"] + 6, round(s_end * fps))

        word_cursor = min(total_words - 1, end_idx + 1)

    # Ensure contiguous frame boundaries with zero gaps
    for i in range(len(scenes) - 1):
        scenes[i + 1]["start_frame"] = scenes[i]["end_frame"] + 1
        if scenes[i + 1]["end_frame"] <= scenes[i + 1]["start_frame"] + 5:
            scenes[i + 1]["end_frame"] = scenes[i + 1]["start_frame"] + 15

    storyboard["total_duration_sec"] = round(scenes[-1]["end_sec"], 3)
    storyboard["fps"] = fps
    return storyboard


def estimate_timestamps_from_storyboard(storyboard: dict[str, Any], output_path: Path) -> dict[str, Any]:
    """Fallback synthetic word timestamps if audio hasn't been generated yet."""
    words: list[dict[str, Any]] = []
    for scene in storyboard.get("scenes", []):
        s_start = float(scene.get("start_sec", 0.0))
        s_end = float(scene.get("end_sec", s_start + 2.5))
        tokens = str(scene.get("narration", "")).split()
        if not tokens:
            continue
        step = (s_end - s_start) / len(tokens)
        for i, tok in enumerate(tokens):
            words.append(
                {
                    "word": tok,
                    "start": round(s_start + i * step, 3),
                    "end": round(s_start + (i + 1) * step, 3),
                }
            )
    data = {
        "text": storyboard.get("full_narration", ""),
        "voice_id": "estimated",
        "total_duration": round(words[-1]["end"], 3) if words else 30.0,
        "words": words,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data
