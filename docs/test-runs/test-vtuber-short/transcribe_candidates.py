"""Source selection: run the registry `transcriber` (faster-whisper) on each candidate."""
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.tool_registry import registry  # noqa: E402

registry.discover()
tr = registry._tools["transcriber"]
print("transcriber status:", tr.get_status())

MEDIA = Path(r"C:\Users\dubia\work\moviemaker-media")
NAMES = [
    "1116.mp4",
    "告知いよるも.mp4",
    "VRChat_20261117_043857 (1).mp4",
    "タイトルなし-2026-11-15 16 41 53(copy).mp4",
]
out_dir = Path(__file__).resolve().parents[1] / "artifacts" / "source_transcripts"
if len(sys.argv) > 1:
    NAMES = [NAMES[int(i)] for i in sys.argv[1:]]
summary = []
for n in NAMES:
    print("start", n, time.strftime("%H:%M:%S"), flush=True)
    t = time.time()
    r = tr.execute({"input_path": str(MEDIA / n), "model_size": "small", "language": "ja", "output_dir": str(out_dir)})
    if not r.success:
        summary.append({"file": n, "error": r.error})
        continue
    d = r.data
    speech = sum(s["end"] - s["start"] for s in d["segments"])
    summary.append({
        "file": n,
        "duration": d["duration_seconds"],
        "segments": len(d["segments"]),
        "speech_seconds": round(speech, 2),
        "device": d["device"],
        "elapsed": round(time.time() - t, 1),
        "text": " / ".join(s["text"] for s in d["segments"]),
    })
(out_dir / ("summary_" + "_".join(sys.argv[1:] or ["all"]) + ".json")).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
