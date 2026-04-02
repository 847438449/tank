#!/usr/bin/env python3
"""Batch transcribe videos in input_videos/ to Japanese text using faster-whisper."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

from faster_whisper import WhisperModel

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov"}
DEFAULT_INPUT_DIR = Path("input_videos")
DEFAULT_OUTPUT_DIR = Path("output")


@dataclass
class SegmentData:
    id: int
    start: float
    end: float
    text: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan videos, extract audio with ffmpeg, and transcribe to Japanese."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Directory containing videos (default: input_videos)",
    )
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
        help="Compute type (default: float16, e.g. int8 / int8_float16 / float32)",
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


def find_videos(input_dir: Path) -> List[Path]:
    if not input_dir.exists():
        raise FileNotFoundError(f"输入目录不存在: {input_dir}")

    videos = [
        p
        for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    ]
    return sorted(videos)


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


def extract_audio(video_path: Path, wav_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
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
            f"ffmpeg 提取音频失败: {video_path.name}\n"
            f"命令: {' '.join(cmd)}\n"
            f"错误输出:\n{completed.stderr.strip()}"
        )


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


def write_json(path: Path, source_video: Path, segments: List[SegmentData], info: dict) -> None:
    data = {
        "source_video": str(source_video),
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


def process_video(model: WhisperModel, video_path: Path, output_dir: Path, beam_size: int) -> None:
    stem = video_path.stem
    txt_path = output_dir / f"{stem}.txt"
    json_path = output_dir / f"{stem}.json"
    srt_path = output_dir / f"{stem}.srt"

    with tempfile.TemporaryDirectory(prefix="audio_extract_") as tmp_dir:
        wav_path = Path(tmp_dir) / f"{stem}.wav"
        extract_audio(video_path, wav_path)
        segments, info = transcribe_audio(model, wav_path, beam_size=beam_size)

    write_txt(txt_path, segments)
    write_json(json_path, video_path, segments, info)
    write_srt(srt_path, segments)


def main() -> int:
    args = parse_args()

    try:
        ensure_ffmpeg()
        videos = find_videos(args.input_dir)

        if not videos:
            print(f"未在 {args.input_dir} 中找到支持的视频文件: {sorted(VIDEO_EXTENSIONS)}")
            return 0

        args.output_dir.mkdir(parents=True, exist_ok=True)

        model, actual_device, actual_compute = create_model_with_fallback(
            model_size=args.model_size,
            device=args.device,
            compute_type=args.compute_type,
        )

        print(
            f"模型加载完成: model={args.model_size}, device={actual_device}, compute_type={actual_compute}"
        )
        print(f"共发现 {len(videos)} 个视频文件，开始处理...")

        for idx, video in enumerate(videos, start=1):
            print(f"[{idx}/{len(videos)}] 处理中: {video}")
            try:
                process_video(model, video, args.output_dir, beam_size=args.beam_size)
            except Exception as exc:
                print(f"[ERROR] 处理失败: {video} -> {exc}", file=sys.stderr)

        print(f"处理完成，输出目录: {args.output_dir.resolve()}")
        return 0

    except KeyboardInterrupt:
        print("用户中断执行。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
