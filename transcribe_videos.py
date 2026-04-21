#!/usr/bin/env python3
"""Transcribe a single local media file or URL to Japanese text with faster-whisper."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Tuple
from urllib.parse import urlparse

from faster_whisper import WhisperModel

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
DEFAULT_OUTPUT_DIR = Path("output")


@dataclass
class SegmentData:
    id: int
    start: float
    end: float
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe one local media file or URL to Japanese text/subtitles."
    )
    parser.add_argument(
        "--mode",
        choices=["local", "url"],
        default="local",
        help="Input mode: local file or URL (default: local)",
    )
    parser.add_argument("--input-file", type=Path, help="Local audio/media file path")
    parser.add_argument("--url", help="Video URL (YouTube first)")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for outputs (default: output)",
    )
    parser.add_argument(
        "--model-size",
        default="small",
        help="faster-whisper model size/name (default: small)",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        choices=["cuda", "cpu"],
        help="Inference device (default: cuda)",
    )
    parser.add_argument(
        "--compute-type",
        default="float16",
        help="Compute type (default: float16, e.g. int8 / float32)",
    )
    parser.add_argument(
        "--beam-size",
        type=int,
        default=5,
        help="Beam size for decoding (default: 5)",
    )
    return parser.parse_args()


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "未找到 ffmpeg。请先安装 ffmpeg 并确保其在 PATH 中。\n"
            "Windows 可使用 winget/choco 安装，或从官网下载安装后加入 PATH。"
        )


def ensure_yt_dlp() -> None:
    if shutil.which("yt-dlp") is None:
        raise RuntimeError(
            "URL 模式需要 yt-dlp，但系统中未找到。\n"
            "请先安装：pip install yt-dlp"
        )


def is_valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def sanitize_filename(name: str, fallback: str = "transcription") -> str:
    """Sanitize output file name for Windows compatibility."""
    cleaned = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        cleaned = fallback

    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
    if cleaned.upper() in reserved:
        cleaned = f"{cleaned}_file"
    return cleaned[:180]


def validate_local_media_file(path: Path) -> Path:
    if not path:
        raise ValueError("未选择本地文件。")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"本地文件不存在: {path}")
    if path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError(
            "不支持的本地音频格式。请使用: "
            + ", ".join(sorted(AUDIO_EXTENSIONS))
        )
    return path


def create_model_with_fallback(model_size: str, device: str, compute_type: str) -> Tuple[WhisperModel, str, str]:
    """Create model and fallback to CPU if CUDA setup fails."""
    try:
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        return model, device, compute_type
    except Exception as exc:
        if device != "cuda":
            raise

        print(
            "[WARN] CUDA 模式初始化失败，将自动回退到 CPU。\n"
            f"       原因: {exc}\n"
            "       你也可以手动指定 --device cpu --compute-type int8",
            file=sys.stderr,
        )

        fallback_compute = "int8" if compute_type != "int8" else compute_type
        model = WhisperModel(model_size, device="cpu", compute_type=fallback_compute)
        return model, "cpu", fallback_compute


def convert_media_to_wav(media_path: Path, wav_path: Path) -> None:
    """Convert any supported media/audio input to mono 16kHz WAV."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(media_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-acodec",
        "pcm_s16le",
        str(wav_path),
    ]
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"ffmpeg 转换音频失败: {media_path.name}\n"
            f"命令: {' '.join(cmd)}\n"
            f"错误输出:\n{completed.stderr.strip()}"
        )


def download_video_from_url(
    url: str,
    download_dir: Path,
    logger: Callable[[str], None] = print,
) -> Path:
    """Download media from URL using yt-dlp and return downloaded file path."""
    ensure_yt_dlp()

    if not is_valid_url(url):
        raise ValueError(f"无效 URL: {url}")

    download_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(download_dir / "%(title).80s [%(id)s].%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--restrict-filenames",
        "-f",
        "bestaudio/best",
        "-o",
        output_template,
        url,
    ]

    logger("开始下载媒体（yt-dlp）...")
    completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "yt-dlp 下载失败。\n"
            f"命令: {' '.join(cmd)}\n"
            f"错误输出:\n{completed.stderr.strip()}"
        )

    downloaded = sorted([p for p in download_dir.iterdir() if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    if not downloaded:
        raise RuntimeError("下载完成但未找到媒体文件。")

    logger(f"下载完成: {downloaded[0]}")
    return downloaded[0]


def transcribe_audio(model: WhisperModel, audio_path: Path, beam_size: int) -> Tuple[List[SegmentData], dict]:
    segments, info = model.transcribe(
        str(audio_path),
        language="ja",
        beam_size=beam_size,
        vad_filter=True,
    )

    seg_list: List[SegmentData] = []
    for idx, seg in enumerate(segments, start=1):
        seg_list.append(
            SegmentData(
                id=idx,
                start=float(seg.start),
                end=float(seg.end),
                text=seg.text.strip(),
            )
        )

    info_dict = {
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "duration_after_vad": info.duration_after_vad,
    }
    return seg_list, info_dict


def format_srt_timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_txt(path: Path, segments: Iterable[SegmentData]) -> None:
    text = "\n".join(seg.text for seg in segments if seg.text)
    path.write_text(text + ("\n" if text else ""), encoding="utf-8")


def write_json(path: Path, source_media: Path, segments: List[SegmentData], info: dict) -> None:
    data = {
        "source_media": str(source_media),
        "language": "ja",
        "model_info": info,
        "segments": [asdict(seg) for seg in segments],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_srt(path: Path, segments: Iterable[SegmentData]) -> None:
    lines: List[str] = []
    for seg in segments:
        if not seg.text:
            continue
        lines.append(str(seg.id))
        lines.append(f"{format_srt_timestamp(seg.start)} --> {format_srt_timestamp(seg.end)}")
        lines.append(seg.text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def save_transcription_outputs(
    output_dir: Path,
    output_stem: str,
    source_media: Path,
    segments: List[SegmentData],
    info: dict,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_stem = sanitize_filename(output_stem, fallback="transcription")

    txt_path = output_dir / f"{safe_stem}.txt"
    json_path = output_dir / f"{safe_stem}.json"
    srt_path = output_dir / f"{safe_stem}.srt"

    write_txt(txt_path, segments)
    write_json(json_path, source_media, segments, info)
    write_srt(srt_path, segments)

    return {"txt": txt_path, "json": json_path, "srt": srt_path}


def transcribe_single_media(
    media_path: Path,
    output_dir: Path,
    model_size: str = "small",
    device: str = "cuda",
    compute_type: str = "float16",
    beam_size: int = 5,
    logger: Callable[[str], None] = print,
    progress_callback: Callable[[int], None] | None = None,
) -> dict[str, Path]:
    if progress_callback:
        progress_callback(45)
    logger("开始提取/转换音频（ffmpeg）...")

    with tempfile.TemporaryDirectory(prefix="single_media_") as tmp_dir:
        wav_path = Path(tmp_dir) / "audio_16k.wav"
        convert_media_to_wav(media_path, wav_path)

        if progress_callback:
            progress_callback(70)
        logger("开始语音识别（faster-whisper, language=ja）...")

        model, actual_device, actual_compute = create_model_with_fallback(
            model_size=model_size,
            device=device,
            compute_type=compute_type,
        )
        logger(
            f"模型加载完成: model={model_size}, device={actual_device}, compute_type={actual_compute}"
        )

        segments, info = transcribe_audio(model, wav_path, beam_size=beam_size)

    if progress_callback:
        progress_callback(90)
    logger("开始保存输出文件（txt/json/srt）...")
    outputs = save_transcription_outputs(
        output_dir=output_dir,
        output_stem=media_path.stem,
        source_media=media_path,
        segments=segments,
        info=info,
    )

    if progress_callback:
        progress_callback(100)
    logger(f"转写完成，输出目录: {output_dir.resolve()}")
    logger(f"已保存: {outputs['txt'].name}, {outputs['json'].name}, {outputs['srt'].name}")
    return outputs


def run_transcription_pipeline(
    input_mode: str,
    input_value: str | Path,
    output_dir: Path,
    model_size: str = "small",
    device: str = "cuda",
    compute_type: str = "float16",
    beam_size: int = 5,
    logger: Callable[[str], None] = print,
    error_logger: Callable[[str], None] | None = None,
    progress_callback: Callable[[int], None] | None = None,
) -> int:
    """Unified single-item pipeline for local audio file or URL input."""
    if error_logger is None:
        error_logger = logger

    try:
        if progress_callback:
            progress_callback(10)

        ensure_ffmpeg()
        if not output_dir:
            raise ValueError("未选择输出目录。")

        output_dir.mkdir(parents=True, exist_ok=True)
        logger("输入已校验。")

        if input_mode == "local":
            media_path = validate_local_media_file(Path(str(input_value)))
            if progress_callback:
                progress_callback(25)
            logger(f"已加载本地音频文件: {media_path}")
            transcribe_single_media(
                media_path=media_path,
                output_dir=output_dir,
                model_size=model_size,
                device=device,
                compute_type=compute_type,
                beam_size=beam_size,
                logger=logger,
                progress_callback=progress_callback,
            )
            return 0

        if input_mode == "url":
            url = str(input_value).strip()
            if not url:
                raise ValueError("URL 不能为空。")
            if not is_valid_url(url):
                raise ValueError(f"无效 URL: {url}")

            if progress_callback:
                progress_callback(25)
            with tempfile.TemporaryDirectory(prefix="url_input_") as tmp_dir:
                download_path = download_video_from_url(
                    url=url,
                    download_dir=Path(tmp_dir),
                    logger=logger,
                )
                transcribe_single_media(
                    media_path=download_path,
                    output_dir=output_dir,
                    model_size=model_size,
                    device=device,
                    compute_type=compute_type,
                    beam_size=beam_size,
                    logger=logger,
                    progress_callback=progress_callback,
                )
            return 0

        raise ValueError(f"不支持的输入模式: {input_mode}")

    except Exception as exc:
        error_logger(f"[FATAL] {exc}")
        raise


def main() -> int:
    args = parse_args()

    try:
        if args.mode == "local":
            if not args.input_file:
                raise ValueError("local 模式需要提供 --input-file")
            return run_transcription_pipeline(
                input_mode="local",
                input_value=args.input_file,
                output_dir=args.output_dir,
                model_size=args.model_size,
                device=args.device,
                compute_type=args.compute_type,
                beam_size=args.beam_size,
                logger=print,
                error_logger=lambda msg: print(msg, file=sys.stderr),
            )

        if args.mode == "url":
            if not args.url:
                raise ValueError("url 模式需要提供 --url")
            return run_transcription_pipeline(
                input_mode="url",
                input_value=args.url,
                output_dir=args.output_dir,
                model_size=args.model_size,
                device=args.device,
                compute_type=args.compute_type,
                beam_size=args.beam_size,
                logger=print,
                error_logger=lambda msg: print(msg, file=sys.stderr),
            )

        raise ValueError(f"不支持的 mode: {args.mode}")

    except KeyboardInterrupt:
        print("用户中断执行。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
