from __future__ import annotations

import asyncio
import json
import math
import struct
import wave
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

from config import detect_ffmpeg_executable

LogCallback = Optional[Callable[[str, str], Coroutine[Any, Any, None]]]


def _format_ass_time(seconds: float) -> str:
    s = max(0.0, float(seconds))
    hrs = int(s // 3600)
    mins = int((s % 3600) // 60)
    secs = int(s % 60)
    cs = int(round((s - int(s)) * 100))
    if cs >= 100:
        secs += 1
        cs = 0
    return f"{hrs}:{mins:02d}:{secs:02d}.{cs:02d}"


def build_ass_subtitles(
    timestamps_data: dict[str, Any],
    output_ass_path: Path,
    *,
    font_name: str = "Montserrat",
    words_per_chunk: int = 3,
) -> Path:
    """
    Generates Zack D. Films-style ASS subtitles for 1080x1920 vertical Shorts, matched to
    the reference Shorts (measured 2026-11-25):
      - Caption centre ~78 % down the frame (bottom of text ~1530 px -> MarginV 390)
      - Heavy rounded sans (Montserrat ExtraBold / Arial Black / Arial Bold fallback),
        ~80 px, pure white, thin dark edge + soft drop shadow (not a thick outline)
      - 2–3 words per caption, never highlighted word-by-word, synced to word timestamps
    """
    words = timestamps_data.get("words", [])
    chunks: list[dict[str, Any]] = []
    i = 0
    while i < len(words):
        # Adaptive 2-3 word chunking (break early on punctuation)
        group = []
        while i < len(words) and len(group) < max(2, min(3, words_per_chunk)):
            w = words[i]
            group.append(w)
            i += 1
            if len(group) >= 2 and str(w.get("word", "")).endswith((".", "!", "?", ",", ";", ":")):
                break
        if group:
            text = " ".join(str(x["word"]).strip() for x in group)
            chunks.append(
                {
                    "text": text,
                    "start": float(group[0]["start"]),
                    "end": float(group[-1]["end"]),
                }
            )

    # Check if Montserrat is installed on Windows, else fall back cleanly to Arial
    win_fonts = Path(r"C:\Windows\Fonts")
    chosen_font = font_name
    if win_fonts.exists():
        names = {p.name.lower() for p in win_fonts.glob("*.ttf")}
        if not any("montserrat" in n for n in names):
            chosen_font = "Arial Black" if "ariblk.ttf" in names else "Arial"

    header = f"""[Script Info]
Title: Stick Knowledge 3D Studio Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ZDFCaption,{chosen_font},80,&H00FFFFFF,&H00FFFFFF,&H40101010,&H78000000,-1,0,0,0,100,100,0,0,1,2.2,3.5,2,70,70,390,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header.strip()]
    for idx, ch in enumerate(chunks):
        st = ch["start"]
        en = ch["end"]
        # Prevent flicker gap if next chunk starts within 0.12s
        if idx + 1 < len(chunks) and chunks[idx + 1]["start"] - en < 0.12:
            en = chunks[idx + 1]["start"]
        en = max(st + 0.18, en)
        clean_txt = ch["text"].replace("{", "").replace("}", "").replace("\n", " ")
        lines.append(
            f"Dialogue: 0,{_format_ass_time(st)},{_format_ass_time(en)},ZDFCaption,,0,0,0,,{clean_txt}"
        )

    output_ass_path.parent.mkdir(parents=True, exist_ok=True)
    output_ass_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_ass_path


def synthesize_transition_sfx_wav(
    cut_times_sec: list[float], total_duration_sec: float, output_wav: Path
) -> Path:
    """
    Synthesizes subtle low-volume whoosh/pop transition SFX aligned to scene cuts
    so Shorts feel crisp and punchy without requiring external copyrighted SFX packs.
    """
    sr = 44100
    total_samples = int(max(1.0, total_duration_sec + 0.5) * sr)
    buf = [0.0] * total_samples

    for t in cut_times_sec:
        if t <= 0.15 or t >= total_duration_sec - 0.1:
            continue
        start_idx = int((t - 0.08) * sr)
        dur_samples = int(0.16 * sr)
        for n in range(dur_samples):
            idx = start_idx + n
            if 0 <= idx < total_samples:
                u = n / max(1, dur_samples - 1)
                env = math.sin(u * math.pi) ** 1.8
                # Soft descending pitch pop + gentle airy whoosh
                freq = 320.0 * (1.0 - 0.55 * u) + 110.0
                tone = math.sin(2.0 * math.pi * freq * (n / sr))
                buf[idx] += tone * env * 0.14

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for sample in buf:
            clamped = max(-0.95, min(0.95, sample))
            frames.extend(struct.pack("<h", int(clamped * 32767)))
        wf.writeframes(bytes(frames))
    return output_wav


class VideoAssembler:
    """
    Assembles rendered Blender PNG sequences (or video clips) + ElevenLabs `narration.mp3`
    + optional subtle transition SFX + Zack D. Films ASS captions into 1080x1920 H.264 `final_short.mp4`.
    """

    def __init__(self) -> None:
        self.ffmpeg = detect_ffmpeg_executable()

    async def assemble_final_short(
        self,
        *,
        project_dir: Path,
        storyboard: dict[str, Any],
        fps: int = 30,
        include_sfx: bool = True,
        burn_captions: bool = True,
        log: LogCallback = None,
    ) -> Path:
        if not self.ffmpeg:
            raise FileNotFoundError("FFmpeg not found in PATH. Install FFmpeg to assemble final_short.mp4.")

        renders_dir = project_dir / "renders"
        audio_path = project_dir / "audio" / "narration.mp3"
        ts_path = project_dir / "audio" / "timestamps.json"
        ass_path = renders_dir / "captions.ass"
        output_mp4 = project_dir / "final_short.mp4"

        # Locate rendered PNG sequence (frame_0001.png ...)
        pngs = sorted(renders_dir.glob("frame_*.png"))
        if not pngs:
            raise FileNotFoundError(f"No rendered frames found in {renders_dir}")

        if burn_captions and ts_path.is_file():
            ts_data = json.loads(ts_path.read_text(encoding="utf-8"))
            build_ass_subtitles(ts_data, ass_path)
            if log:
                await log("ffmpeg", f"Generated Zack D. Films ASS captions -> {ass_path.name}")

        # Build FFmpeg command
        cmd: list[str] = [
            self.ffmpeg,
            "-y",
            "-framerate",
            str(fps),
            "-start_number",
            "1",
            "-i",
            str(renders_dir / "frame_%04d.png"),
        ]

        has_audio = audio_path.is_file()
        sfx_wav: Optional[Path] = None
        if has_audio:
            cmd.extend(["-i", str(audio_path)])
            if include_sfx:
                cut_times = [float(s.get("start_sec", 0.0)) for s in storyboard.get("scenes", [])[1:]]
                total_dur = float(storyboard.get("total_duration_sec", len(pngs) / fps))
                sfx_wav = synthesize_transition_sfx_wav(cut_times, total_dur, renders_dir / "transitions_sfx.wav")
                cmd.extend(["-i", str(sfx_wav)])

        # Video filter (scale safety + ASS subtitles burn-in)
        vf_parts = ["scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"]
        if burn_captions and ass_path.is_file():
            # Escape Windows drive colon and backslashes for FFmpeg ass filter
            escaped_ass = str(ass_path).replace("\\", "/").replace(":", "\\:")
            vf_parts.append(f"ass='{escaped_ass}'")
        cmd.extend(["-vf", ",".join(vf_parts)])

        if has_audio and sfx_wav:
            cmd.extend(
                [
                    "-filter_complex",
                    "[1:a]volume=1.0[voice];[2:a]volume=0.35[sfx];[voice][sfx]amix=inputs=2:duration=first:dropout_transition=0[aout]",
                    "-map",
                    "0:v:0",
                    "-map",
                    "[aout]",
                ]
            )
        elif has_audio:
            cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])
        else:
            cmd.extend(["-map", "0:v:0"])

        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(fps),
            ]
        )
        if has_audio:
            cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])

        cmd.extend(["-movflags", "+faststart", str(output_mp4)])

        if log:
            await log("ffmpeg", f"Assembling 1080x1920 final Short -> {output_mp4}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout is not None
        lines = []
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip()
            lines.append(line)
            if log and ("frame=" in line or "error" in line.lower()):
                await log("ffmpeg", line)

        rc = await proc.wait()
        if rc != 0 or not output_mp4.is_file():
            raise RuntimeError(f"FFmpeg assembly failed (exit {rc}):\n" + "\n".join(lines[-20:]))

        if log:
            await log("ffmpeg", f"Final Short ready: {output_mp4} ({output_mp4.stat().st_size // 1024} KB)")
        return output_mp4
