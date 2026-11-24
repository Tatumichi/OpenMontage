"""Transcription tool wrapping faster-whisper / WhisperX.

Provides speech-to-text with word-level timestamps and optional speaker
diarization. Falls back gracefully when GPU or diarization dependencies
are not available.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ResumeSupport,
    ToolResult,
    ToolStability,
    ToolStatus,
    ToolTier,
)


_DEFAULT_TIMEOUT_SECONDS = 1800


class Transcriber(BaseTool):
    name = "transcriber"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "analysis"
    provider = "whisperx"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC

    dependencies = ["python:faster_whisper"]
    install_instructions = (
        "pip install faster-whisper  # CPU mode\n"
        "pip install faster-whisper[gpu]  # GPU mode (requires CUDA)\n"
        "pip install whisperx  # For diarization support"
    )
    agent_skills = ["speech-to-text"]

    capabilities = [
        "transcribe",
        "word_timestamps",
        "diarization",
        "language_detection",
    ]

    input_schema = {
        "type": "object",
        "required": ["input_path"],
        "properties": {
            "input_path": {"type": "string", "description": "Path to audio or video file"},
            "model_size": {
                "type": "string",
                "enum": ["tiny", "base", "small", "medium", "large-v2", "large-v3"],
                "default": "base",
            },
            "language": {"type": "string", "description": "ISO 639-1 language code, or null for auto-detect"},
            "timeout_seconds": {
                "type": "integer",
                "minimum": 1,
                "default": _DEFAULT_TIMEOUT_SECONDS,
                "description": "Time limit for transcription, including model loading and diarization",
            },
            "diarize": {"type": "boolean", "default": False},
            "output_dir": {"type": "string", "description": "Directory for output files"},
        },
    }

    output_schema = {
        "type": "object",
        "properties": {
            "segments": {"type": "array"},
            "word_timestamps": {"type": "array"},
            "language": {"type": "string"},
            "duration_seconds": {"type": "number"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=2,
        ram_mb=2048,
        vram_mb=0,  # CPU by default; GPU optional
        disk_mb=500,
        network_required=False,
    )

    retry_policy = RetryPolicy(max_retries=1, retryable_errors=["MemoryError"])
    resume_support = ResumeSupport.FROM_START
    idempotency_key_fields = ["input_path", "model_size", "language"]
    side_effects = ["writes transcript JSON to output_dir"]
    fallback = None
    user_visible_verification = [
        "Check transcript text against source audio",
        "Verify word timestamps align with speech",
    ]

    def get_status(self) -> ToolStatus:
        try:
            import faster_whisper  # noqa: F401
            return ToolStatus.AVAILABLE
        except ImportError:
            return ToolStatus.UNAVAILABLE

    def _has_diarization(self) -> bool:
        try:
            import whisperx  # noqa: F401
            return True
        except ImportError:
            return False

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        """Rough estimate: ~0.5x real-time on CPU for 'base' model."""
        return 60.0  # conservative default

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        input_path = Path(inputs["input_path"])
        if not input_path.exists():
            return ToolResult(success=False, error=f"Input file not found: {input_path}")

        raw_timeout = inputs.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
        timeout_error = "timeout_seconds must be a positive integer"
        if isinstance(raw_timeout, bool):
            return ToolResult(success=False, error=timeout_error)
        try:
            timeout = int(raw_timeout)
        except (TypeError, ValueError, OverflowError):
            return ToolResult(success=False, error=timeout_error)
        if timeout < 1:
            return ToolResult(success=False, error=timeout_error)

        request = {
            "input_path": str(input_path.resolve()),
            "model_size": inputs.get("model_size", "base"),
            "language": inputs.get("language"),
            "diarize": inputs.get("diarize", False),
        }

        # A native decoder or model call can block. Keep it in a child process
        # so the timeout can stop it, and inherit stderr for live progress logs.
        with tempfile.TemporaryDirectory(prefix="openmontage-transcriber-") as directory:
            result_path = Path(directory) / "result.json"
            try:
                process = subprocess.run(
                    [sys.executable, "-m", "tools.analysis.transcriber", str(result_path)],
                    input=json.dumps(request),
                    stdout=subprocess.PIPE,
                    cwd=Path(__file__).resolve().parents[2],
                    env={**os.environ, "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"},
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                return ToolResult(success=False, error=f"Transcription timed out after {timeout}s")
            except OSError as exc:
                return ToolResult(success=False, error=f"Could not start transcription: {exc}")
            if process.returncode:
                return ToolResult(
                    success=False, error=f"Transcription worker exited with code {process.returncode}",
                )
            # The worker sends errors over stdout if writing the result file fails.
            payload = process.stdout or result_path.read_text(encoding="utf-8")
            result = ToolResult(**json.loads(payload))

        if result.success:
            output_dir = Path(inputs.get("output_dir", input_path.parent))
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{input_path.stem}_transcript.json"
            output_path.write_text(json.dumps(result.data, indent=2), encoding="utf-8")
            result.artifacts.append(str(output_path))
        return result

    def _transcribe(self, inputs: dict[str, Any]) -> ToolResult:
        input_path = Path(inputs["input_path"])
        model_size = inputs.get("model_size", "base")
        language = inputs.get("language")
        diarize = inputs.get("diarize", False)

        print("[transcriber] Initializing faster-whisper", file=sys.stderr, flush=True)
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            return ToolResult(
                success=False,
                error="faster-whisper is not installed. Run: pip install faster-whisper",
            )

        start = time.monotonic()

        # faster-whisper executes through CTranslate2, so that runtime—not
        # PyTorch—is authoritative for CUDA availability and compute types.
        device = "cpu"
        compute_type = "int8"
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() > 0:
                supported = ctranslate2.get_supported_compute_types("cuda")
                for candidate in ("float16", "int8_float16", "float32"):
                    if candidate in supported:
                        device = "cuda"
                        compute_type = candidate
                        break
        except Exception:
            # Probing is advisory. CPU remains a safe deterministic baseline.
            pass

        def _transcribe_on(selected_device: str, selected_compute_type: str):
            print(
                f"[transcriber] Loading {model_size} model on {selected_device}",
                file=sys.stderr,
                flush=True,
            )
            model = WhisperModel(
                model_size,
                device=selected_device,
                compute_type=selected_compute_type,
            )
            print("[transcriber] Decoding and transcribing audio", file=sys.stderr, flush=True)
            segments_iter, transcription_info = model.transcribe(
                str(input_path),
                language=language,
                word_timestamps=True,
                vad_filter=True,
            )

            parsed_segments = []
            parsed_words = []
            # faster-whisper evaluates lazily. Draining the iterator here keeps
            # missing CUDA runtime libraries inside the fallback boundary.
            next_progress = 0.0
            for seg in segments_iter:
                if seg.end >= next_progress:
                    print(
                        f"[transcriber] Transcribed through {seg.end:.1f}s of audio",
                        file=sys.stderr,
                        flush=True,
                    )
                    next_progress = seg.end + 30
                seg_data = {
                    "id": seg.id,
                    "start": round(seg.start, 3),
                    "end": round(seg.end, 3),
                    "text": seg.text.strip(),
                }

                if seg.words:
                    words = []
                    for word in seg.words:
                        word_entry = {
                            "word": word.word,
                            "start": round(word.start, 3),
                            "end": round(word.end, 3),
                            "probability": round(word.probability, 3),
                        }
                        words.append(word_entry)
                        parsed_words.append(word_entry)
                    seg_data["words"] = words

                parsed_segments.append(seg_data)

            return parsed_segments, parsed_words, transcription_info

        gpu_fallback_reason = None
        try:
            segments, word_timestamps, info = _transcribe_on(device, compute_type)
        except Exception as exc:
            if device == "cpu":
                raise
            gpu_fallback_reason = f"{type(exc).__name__}: {exc}"
            print("[transcriber] CUDA failed, retrying on CPU", file=sys.stderr, flush=True)
            device = "cpu"
            compute_type = "int8"
            segments, word_timestamps, info = _transcribe_on(device, compute_type)

        detected_language = language or info.language
        duration = info.duration

        # Optional diarization pass
        if diarize and self._has_diarization():
            print("[transcriber] Running speaker diarization", file=sys.stderr, flush=True)
            segments = self._apply_diarization(
                str(input_path), segments, detected_language
            )

        elapsed = time.monotonic() - start

        result_data = {
            "segments": segments,
            "word_timestamps": word_timestamps,
            "language": detected_language,
            "duration_seconds": round(duration, 3),
            "model_size": model_size,
            "device": device,
            "compute_type": compute_type,
            "gpu_fallback_reason": gpu_fallback_reason,
        }

        print(f"[transcriber] Finished in {elapsed:.1f}s", file=sys.stderr, flush=True)
        return ToolResult(
            success=True,
            data=result_data,
            duration_seconds=round(elapsed, 2),
        )

    def _apply_diarization(
        self,
        audio_path: str,
        segments: list[dict],
        language: str,
    ) -> list[dict]:
        """Apply WhisperX diarization to assign speaker labels."""
        try:
            import whisperx

            # Load audio for alignment
            audio = whisperx.load_audio(audio_path)

            # Align segments with word timestamps
            align_model, align_metadata = whisperx.load_align_model(
                language_code=language, device="cpu"
            )
            aligned = whisperx.align(
                segments, align_model, align_metadata, audio, device="cpu"
            )

            # Diarize
            import os
            hf_token = os.environ.get("HF_TOKEN")
            if not hf_token:
                # Can't diarize without HuggingFace token for pyannote
                return segments

            diarize_model = whisperx.DiarizationPipeline(
                use_auth_token=hf_token, device="cpu"
            )
            diarize_segments = diarize_model(audio)
            result = whisperx.assign_word_speakers(diarize_segments, aligned)

            return result.get("segments", segments)
        except Exception:
            # Diarization is best-effort; return original segments on failure
            return segments


if __name__ == "__main__":
    # Send transcription logs to stderr and reserve stdout for fallback errors.
    from contextlib import redirect_stdout

    try:
        request = json.load(sys.stdin)
        with redirect_stdout(sys.stderr):
            result = Transcriber()._transcribe(request)
    except Exception as exc:
        result = ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")
    try:
        Path(sys.argv[1]).write_text(json.dumps(asdict(result)), encoding="utf-8")
    except Exception as exc:
        print(json.dumps({
            "success": False,
            "error": f"Could not save transcription worker result: {type(exc).__name__}: {exc}",
        }), flush=True)
