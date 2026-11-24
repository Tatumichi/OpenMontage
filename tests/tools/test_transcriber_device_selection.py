import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.analysis.transcriber import Transcriber


class _Info:
    language = "en"
    duration = 1.0


def test_transcriber_uses_ctranslate2_cuda_without_torch(monkeypatch, tmp_path) -> None:
    devices = []

    class FakeWhisperModel:
        def __init__(self, model_size, *, device, compute_type):
            devices.append((device, compute_type))

        def transcribe(self, *args, **kwargs):
            return iter(()), _Info()

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=FakeWhisperModel),
    )
    monkeypatch.setitem(
        sys.modules,
        "ctranslate2",
        SimpleNamespace(
            get_cuda_device_count=lambda: 1,
            get_supported_compute_types=lambda device: {"float16", "float32"},
        ),
    )
    input_path = tmp_path / "audio.wav"
    input_path.write_bytes(b"fake")

    result = Transcriber()._transcribe({"input_path": str(input_path)})

    assert result.success, result.error
    assert devices == [("cuda", "float16")]
    assert result.data["device"] == "cuda"


def test_transcriber_falls_back_when_cuda_fails_during_iteration(monkeypatch, tmp_path) -> None:
    devices = []

    class FakeWhisperModel:
        def __init__(self, model_size, *, device, compute_type):
            self.device = device
            devices.append((device, compute_type))

        def transcribe(self, *args, **kwargs):
            if self.device == "cuda":
                def broken_iterator():
                    raise RuntimeError("cublas64_12.dll not found")
                    yield

                return broken_iterator(), _Info()
            return iter(()), _Info()

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=FakeWhisperModel),
    )
    monkeypatch.setitem(
        sys.modules,
        "ctranslate2",
        SimpleNamespace(
            get_cuda_device_count=lambda: 1,
            get_supported_compute_types=lambda device: {"float16"},
        ),
    )
    input_path = tmp_path / "audio.wav"
    input_path.write_bytes(b"fake")

    result = Transcriber()._transcribe({"input_path": str(input_path)})

    assert result.success, result.error
    assert devices == [("cuda", "float16"), ("cpu", "int8")]
    assert result.data["device"] == "cpu"
    assert "cublas64_12.dll" in result.data["gpu_fallback_reason"]


@pytest.mark.parametrize(
    ("options", "expected_timeout"),
    [({}, 1800), ({"timeout_seconds": 600.0}, 600), ({"timeout_seconds": True}, None)],
)
def test_transcriber_worker_timeout_validation(monkeypatch, tmp_path, options, expected_timeout):
    import tempfile

    input_path = tmp_path / "audio.wav"
    input_path.touch()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    timeouts = []

    def fake_run(args, *, timeout, **kwargs):
        timeouts.append(timeout)
        Path(args[-1]).write_text('{"success": false, "error": "test worker"}', encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, stdout="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = Transcriber().execute({"input_path": str(input_path), **options})
    assert not result.success
    if expected_timeout is None:
        assert not timeouts
        assert result.error == "timeout_seconds must be a positive integer"
    else:
        assert timeouts == [expected_timeout]
        assert type(timeouts[0]) is int
        assert result.error == "test worker"


@pytest.fixture
def transcriber_worker_input(monkeypatch, tmp_path):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    (tmp_path / "ctranslate2.py").write_text("def get_cuda_device_count(): return 0\n")
    (tmp_path / "faster_whisper.py").write_text(
        """
import sys
import time
from pathlib import Path
from types import SimpleNamespace

class WhisperModel:
    def __init__(self, model_size, **kwargs):
        assert sys.flags.utf8_mode == 1
        assert sys.stdout.write_through
        if model_size == "large-v3":
            time.sleep(30)
        if model_size == "small":
            def fail_write(*args, **kwargs):
                raise OSError("simulated worker write failure")

            Path.write_text = fail_write

    def transcribe(self, *args, **kwargs):
        segment = SimpleNamespace(id=0, start=0.0, end=1.0, text="\u65e5\u672c\u8a9e", words=[])
        return iter([segment]), SimpleNamespace(language="ja", duration=1.0)
""",
        encoding="utf-8",
    )
    input_path = tmp_path / "\u97f3\u58f0.wav"
    input_path.touch()
    return input_path


def test_transcriber_worker_returns_transcript_and_stops_on_timeout(transcriber_worker_input, capfd):
    import json

    input_path = transcriber_worker_input
    tool = Transcriber()
    result = tool.execute({"input_path": str(input_path)})
    assert result.success, result.error
    transcript = input_path.with_name(f"{input_path.stem}_transcript.json")
    assert result.artifacts == [str(transcript)]
    assert json.loads(transcript.read_text(encoding="utf-8"))["segments"][0]["text"] == "\u65e5\u672c\u8a9e"
    assert "Transcribed through 1.0s" in capfd.readouterr().err

    result = tool.execute(
        {"input_path": str(input_path), "model_size": "large-v3", "timeout_seconds": 2}
    )
    assert not result.success
    assert result.error == "Transcription timed out after 2s"
    assert "Loading large-v3 model" in capfd.readouterr().err


def test_transcriber_worker_reports_write_failure(transcriber_worker_input):
    result = Transcriber().execute(
        {"input_path": str(transcriber_worker_input), "model_size": "small"}
    )

    assert not result.success
    assert result.error == (
        "Could not save transcription worker result: OSError: simulated worker write failure"
    )
    assert not result.artifacts
