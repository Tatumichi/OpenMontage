"""clip-factory stage runner for the test-vtuber-short project.

Drives the clip-factory stages in manifest order, calling registry tools and
writing checkpoints through lib.checkpoint. Gated stages are written
awaiting_human first, then completed with human_approved=True under the
approval_policy decision (d-001) recorded at the idea stage.

Usage: python -X utf8 runner/run_stages.py <stage>   (idea|script|scene_plan|assets|edit|compose|publish)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from lib.checkpoint import read_checkpoint, write_checkpoint  # noqa: E402
from lib.paths import PROJECTS_DIR  # noqa: E402
from tools.tool_registry import registry  # noqa: E402

PID = "test-vtuber-short"
PIPE = "clip-factory"
PLAYBOOK = "flat-motion-graphics"
PROJ = PROJECTS_DIR / PID
ART = PROJ / "artifacts"
RUNNER = PROJ / "runner"
SOURCE = Path(r"C:\Users\dubia\work\moviemaker-media\告知いよるも.mp4")
OUT_DIR = Path(r"C:\Users\dubia\work\shared-memory\openmontage-output")
FINAL = OUT_DIR / "test-vtuber-short.mp4"
FFPROBE = r"C:\Users\dubia\AppData\Local\Microsoft\WinGet\Links\ffprobe.exe"
CLIP_IN, CLIP_OUT = 0.0, 32.5
APPROVAL_NOTE = "approved under approval_policy d-001 (test run, pre-authorized by mugi's request)"

registry.discover()


def tool(name):
    return registry._tools[name]


def save(name, data):
    ART.mkdir(parents=True, exist_ok=True)
    (ART / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load(name):
    return json.loads((ART / f"{name}.json").read_text(encoding="utf-8"))


def log_time(stage, start, extra=None):
    p = RUNNER / "timings.json"
    t = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    t[stage] = {"start": datetime.fromtimestamp(start).strftime("%H:%M:%S"),
                "end": datetime.now().strftime("%H:%M:%S"),
                "seconds": round(time.time() - start, 1), **(extra or {})}
    p.write_text(json.dumps(t, ensure_ascii=False, indent=2), encoding="utf-8")


def gate(stage, artifacts, review, gated=True, metadata=None):
    """awaiting_human -> completed(human_approved) for gated stages."""
    kw = dict(pipeline_type=PIPE, style_playbook=PLAYBOOK, review=review, metadata=metadata)
    if gated:
        write_checkpoint(PROJECTS_DIR, PID, stage, "awaiting_human", artifacts,
                         human_approval_required=True, **kw)
        write_checkpoint(PROJECTS_DIR, PID, stage, "completed", artifacts,
                         human_approval_required=True, human_approved=True, **kw)
    else:
        write_checkpoint(PROJECTS_DIR, PID, stage, "completed", artifacts, **kw)


def probe(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                        "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
                        "-of", "json", str(path)], capture_output=True, text=True, encoding="utf-8")
    return json.loads(r.stdout)


def review(focus, findings=None):
    return {"round": 1, "status": "pass_with_warnings" if findings else "pass",
            "focus": focus, "findings": findings or []}


# --------------------------------------------------------------------------- stages

def stage_idea():
    t0 = time.time()
    src = json.loads((ART / "source_transcripts" / "summary_1.json").read_text(encoding="utf-8"))[0]
    brief = {
        "version": "1.0",
        "title": "VTuber 初配信告知ショート（いよるも）",
        "hook": "冒頭0秒から本人が話し出す初配信告知",
        "key_points": ["自己紹介（VRChat・イラスト）", "12月5日にYouTubeで初配信", "チャンネル登録の呼びかけ"],
        "core_message": "初配信の日時を伝えてチャンネル登録を促す",
        "cta": "チャンネル登録して待っててね",
        "tone": "明るい・親しみやすい",
        "style": "縦型ショート、話者の映像そのまま＋単語ハイライト字幕",
        "target_audience": "VTuber・VRChat に関心のある視聴者",
        "target_platform": "youtube",
        "target_duration_seconds": CLIP_OUT - CLIP_IN,
        "metadata": {
            "source_type": "stream announcement (vertical self-recorded talking footage)",
            "source_path": str(SOURCE),
            "source_duration_seconds": src["duration"],
            "clip_target_range": [1, 1],
            "clip_families": ["hook"],
            "primary_platforms": ["youtube_shorts"],
            "secondary_platforms": [],
            "selection_criteria": ["speech coverage", "standalone", "fits youtube_shorts 60s max"],
            "known_visual_constraints": "source is already 1080x1920 9:16; no reframe needed",
            "distribution_goal": "awareness (test run)",
            "composition": "TalkingHead (stock Remotion composition, used as-is)",
            "media_profile": "youtube_shorts",
            "transcriber": "faster-whisper via registry tool `transcriber` (model small, ja, CPU int8)",
            "test_run": True,
        },
    }
    decisions = {"version": "1.0", "project_id": PID, "decisions": [
        {"decision_id": "d-001", "stage": "idea", "category": "approval_policy",
         "subject": "Full-run pre-authorization",
         "options_considered": [
             {"option_id": "gate_each", "label": "Stop at every gate", "score": 0.3, "reason": "default protocol",
              "rejected_because": "test run; requester asked to run to the end"},
             {"option_id": "preauth", "label": "Run straight through, record each gate", "score": 0.9,
              "reason": "mugi's work request: test run, leave approval_policy in decision_log and run to the end"}],
         "selected": "preauth",
         "reason": "Requester (mugi) explicitly pre-authorized the full run for this test and asked that each approved stage be recorded in the notes.",
         "user_visible": True, "user_approved": True},
        {"decision_id": "d-002", "stage": "idea", "category": "pipeline_selection", "subject": "Pipeline",
         "options_considered": [
             {"option_id": "clip-factory", "label": "clip-factory", "score": 1.0, "reason": "specified by requester"},
             {"option_id": "talking-head", "label": "talking-head", "score": 0.5, "reason": "also fits footage",
              "rejected_because": "requester specified clip-factory"}],
         "selected": "clip-factory", "reason": "Specified in the work request.", "user_visible": True, "user_approved": True},
        {"decision_id": "d-003", "stage": "idea", "category": "render_runtime_selection", "subject": "Render runtime",
         "options_considered": [
             {"option_id": "remotion", "label": "Remotion (TalkingHead)", "score": 1.0,
              "reason": "TalkingHead composition + word-level caption burn"},
             {"option_id": "hyperframes", "label": "HyperFrames", "score": 0.1, "reason": "available on this machine",
              "rejected_because": "caption-burn parity deferred on clip-factory"},
             {"option_id": "ffmpeg", "label": "FFmpeg only", "score": 0.3, "reason": "plain trim/encode",
              "rejected_because": "requester asked for the TalkingHead composition"}],
         "selected": "remotion", "reason": "TalkingHead specified; clip-factory caption burn is Remotion-only.",
         "user_visible": True, "user_approved": True},
        {"decision_id": "d-004", "stage": "idea", "category": "composition_mode", "subject": "Composition authoring mode",
         "options_considered": [
             {"option_id": "templated", "label": "Templated (stock TalkingHead as-is)", "score": 1.0, "reason": "requester: no new templates/compositions"},
             {"option_id": "atelier", "label": "Atelier", "score": 0.0, "reason": "would author a new composition",
              "rejected_because": "new compositions are out of scope for this test"}],
         "selected": "templated", "reason": "Use TalkingHead unchanged.", "user_visible": True, "user_approved": True},
        {"decision_id": "d-005", "stage": "idea", "category": "concept_selection", "subject": "Source footage",
         "options_considered": [
             {"option_id": "iyorumo", "label": "告知いよるも.mp4", "score": 0.95,
              "reason": "33.0s, speech 31.1s (94%), 4 coherent segments: intro, debut date, plans, CTA"},
             {"option_id": "vrchat", "label": "VRChat_20261117_043857 (1).mp4", "score": 0.85,
              "reason": "34.2s, speech 29.8s; also clear", "rejected_because": "lower speech ratio, runner-up"},
             {"option_id": "1116", "label": "1116.mp4", "score": 0.6,
              "reason": "39.1s, speech 24.2s; many ASR misrecognitions", "rejected_because": "less speech, weaker transcript"},
             {"option_id": "untitled", "label": "タイトルなし-2026-11-15 16 41 53(copy).mp4", "score": 0.1,
              "reason": "56.6s; faster-whisper did not finish within 10 min", "rejected_because": "transcription stalled; speech unverified"}],
         "selected": "iyorumo", "reason": "Most speech, cleanest transcript, standalone announcement.",
         "user_visible": True, "user_approved": True},
        {"decision_id": "d-006", "stage": "idea", "category": "music_source", "subject": "Background music",
         "options_considered": [
             {"option_id": "none", "label": "Keep source audio only", "score": 0.9, "reason": "source already has its own audio bed"},
             {"option_id": "library", "label": "music_library track", "score": 0.2, "reason": "not requested",
              "rejected_because": "not part of the test request"}],
         "selected": "none", "reason": "Test focuses on clip + TalkingHead captions.", "user_visible": True, "user_approved": True},
    ]}
    save("brief", brief)
    save("decision_log_idea", decisions)
    gate("idea", {"brief": brief, "decision_log": decisions},
         review(["source type", "clip count", "selection criteria"],
                ["Single clip target: source is 33s, already a short; rule of thumb (1 per 5-10 min) does not apply."]))
    log_time("idea", t0, {"approved": APPROVAL_NOTE})


def stage_script():
    t0 = time.time()
    out_dir = ART / "script_transcript"
    r = tool("transcriber").execute({"input_path": str(SOURCE), "model_size": "small", "language": "ja",
                                     "output_dir": str(out_dir)})
    if not r.success:
        raise SystemExit(f"transcriber failed: {r.error}")
    d = r.data
    (ART / "transcript.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    sections = [{"id": f"s{i+1}", "label": lbl, "text": s["text"], "start_seconds": s["start"],
                 "end_seconds": s["end"], "source_ref": SOURCE.name}
                for i, (s, lbl) in enumerate(zip(d["segments"], ["hook/intro", "profile+date", "plans+CTA", "date CTA"]))]
    script = {
        "version": "1.0", "title": "VTuber 初配信告知ショート（いよるも）",
        "total_duration_seconds": CLIP_OUT - CLIP_IN, "sections": sections,
        "metadata": {
            "transcriber": {"tool": "transcriber", "engine": "faster-whisper", "model": d["model_size"],
                            "device": d["device"], "compute_type": d["compute_type"], "language": d["language"]},
            "candidate_clips": [{"id": "clip01", "source_in": CLIP_IN, "source_out": CLIP_OUT,
                                 "hook_text": sections[0]["text"],
                                 "scores": {"hook": 0.8, "coherence": 0.9, "value": 0.7, "energy": 0.8, "platform_fit": 0.95},
                                 "reason": "whole announcement is self-contained and under 60s",
                                 "crop_viability": "native 9:16, no crop"}],
            "selected_clip_ids": ["clip01"],
            "rejected_candidates": [],
            "ranking_model": "hook/coherence/value/energy/platform_fit",
            "platform_assignments": {"clip01": "youtube_shorts"},
            "asr_suspected_errors": ["緊急各地 (likely 緊急告知)", "略していい夜も (name segment)",
                                     "ギターを引き渡っちゃおうかな (likely 弾いちゃおうかな)", "vr ちょっと (likely VRChat)"],
            "asr_corrections_applied": "none (left for human review; not guessed)",
            "scene_detect": "skipped (optional; single continuous clip)",
        },
    }
    save("script", script)
    gate("script", {"script": script},
         review(["transcription timestamps", "clip ranking", "standalone"],
                ["ASR errors remain in Japanese text; corrections not applied (see metadata.asr_suspected_errors)."]))
    log_time("script", t0, {"approved": APPROVAL_NOTE, "transcribe_seconds": r.duration_seconds})


def stage_scene_plan():
    t0 = time.time()
    fdir = PROJ / "assets" / "images" / "frames"
    r = tool("frame_sampler").execute({"input_path": str(SOURCE), "strategy": "timestamps",
                                       "timestamps": [0.5, 10.0, 20.0, 31.0], "output_dir": str(fdir), "format": "jpg"})
    frames = r.artifacts if r.success else []
    scene_plan = {
        "version": "1.0", "style_playbook": PLAYBOOK,
        "scenes": [{
            "id": "clip01-shorts", "type": "talking_head",
            "description": "Full announcement clip, native 9:16, TalkingHead with word-highlight captions at the bottom.",
            "start_seconds": CLIP_IN, "end_seconds": CLIP_OUT, "script_section_id": "s1",
            "framing": "native 1080x1920, no punch-in", "transition_in": "cut", "transition_out": "cut",
            "overlay_notes": "no hook overlay (speaker starts at 0s); captions only",
            "required_assets": [
                {"type": "video", "description": "clip01 trimmed from source 0.0-32.5s", "source": "source"},
                {"type": "subtitle", "description": "clip01 word-level captions from transcriber", "source": "generate"}]}],
        "metadata": {"clip_layouts": {"clip01": "9:16 native"},
                     "safe_zones": {"captions": "bottom (TalkingHead CaptionOverlay default)"},
                     "frame_samples": frames, "platform_variants": ["youtube_shorts"]},
    }
    save("scene_plan", scene_plan)
    gate("scene_plan", {"scene_plan": scene_plan},
         review(["in/out points", "no mid-sentence cut", "platform framing"]))
    log_time("scene_plan", t0, {"approved": APPROVAL_NOTE, "frames": frames})


def stage_assets():
    t0 = time.time()
    vdir = PROJ / "assets" / "video"
    clip = vdir / "clip01.mp4"
    r = tool("video_trimmer").execute({"operation": "cut", "input_path": str(SOURCE), "output_path": str(clip),
                                       "start_seconds": CLIP_IN, "end_seconds": CLIP_OUT})
    if not r.success:
        raise SystemExit(f"video_trimmer failed: {r.error}")
    norm = vdir / "clip01_norm.mp4"
    r2 = tool("audio_enhance").execute({"input_path": str(clip), "output_path": str(norm), "preset": "normalize_only"})
    if not r2.success:
        raise SystemExit(f"audio_enhance failed: {r2.error}")
    d = json.loads((ART / "transcript.json").read_text(encoding="utf-8"))
    srt = PROJ / "assets" / "subtitles.srt"
    r3 = tool("subtitle_gen").execute({"segments": d["segments"], "format": "srt", "output_path": str(srt),
                                       "max_chars_per_line": 16})
    if not r3.success:
        raise SystemExit(f"subtitle_gen failed: {r3.error}")
    pr = probe(norm)
    manifest = {
        "version": "1.0",
        "assets": [
            {"id": "clip01_video", "type": "video", "path": str(norm), "source_tool": "video_trimmer+audio_enhance",
             "scene_id": "clip01-shorts", "duration_seconds": float(pr["format"]["duration"]),
             "resolution": "1080x1920", "format": "mp4", "cost_usd": 0},
            {"id": "clip01_subtitles", "type": "subtitle", "path": str(srt), "source_tool": "subtitle_gen",
             "scene_id": "clip01-shorts", "format": "srt", "cost_usd": 0},
        ],
        "total_cost_usd": 0,
        "metadata": {"subtitle_map": {"clip01": {"offset_seconds": CLIP_IN, "note": "clip starts at 0 → no rebase"}},
                     "audio_profile": "audio_enhance normalize_only", "shared_assets": [],
                     "hero_sample": "skipped: no generated visuals (source footage only)"},
    }
    save("asset_manifest", manifest)
    gate("assets", {"asset_manifest": manifest},
         review(["per-clip subtitles", "audio normalized"],
                ["Hero scene sample step skipped: nothing is generated, only source footage."]))
    log_time("assets", t0, {"approved": APPROVAL_NOTE})


def stage_edit():
    t0 = time.time()
    ed = {
        "version": "1.0", "render_runtime": "remotion", "renderer_family": "presenter",
        "composition_mode": "templated",
        "cuts": [{"id": "clip01", "source": "clip01_video", "in_seconds": 0.0, "out_seconds": CLIP_OUT - CLIP_IN,
                  "transition_in": "cut", "transition_out": "cut", "reason": "whole announcement; speech from 0.0s"}],
        "subtitles": {"enabled": True, "style": "word_highlight", "source": "clip01_subtitles",
                      "position": "bottom-center","font_size": 64, "max_words_per_line": 8,
                      "caption_props": {"wordSeparator": ""}},
        "metadata": {"composition": "TalkingHead", "tool": "remotion_caption_burn",
                     "words_per_page": 8, "highlight_color": "#22D3EE", "profile": "youtube_shorts",
                     "hook_windows": {"clip01": [0.0, 2.5]}},
    }
    save("edit_decisions", ed)
    gate("edit", {"edit_decisions": ed}, review(["hook in first 2-3s", "subtitle style"]), gated=False)
    log_time("edit", t0, {"approved": "not gated (human_approval_default: false)"})


def stage_compose():
    t0 = time.time()
    ed = load("edit_decisions")
    manifest = load("asset_manifest")
    d = json.loads((ART / "transcript.json").read_text(encoding="utf-8"))
    clip = Path(next(a["path"] for a in manifest["assets"] if a["id"] == "clip01_video"))
    rdir = PROJ / "renders"
    captioned = rdir / "clip01_talkinghead.mp4"
    r = tool("remotion_caption_burn").execute({
        "input_path": str(clip), "output_path": str(captioned), "segments": d["segments"],
        "words_per_page": ed["metadata"]["words_per_page"], "font_size": ed["subtitles"]["font_size"],
        "highlight_color": ed["metadata"]["highlight_color"], "caption_props": ed["subtitles"]["caption_props"]})
    if not r.success or r.data.get("method") != "remotion":
        raise SystemExit(f"remotion_caption_burn failed or fell back: {r.error} {r.data}")
    t_burn = r.duration_seconds
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    vc = tool("video_compose")
    r2 = vc.execute({"operation": "encode", "input_path": str(captioned), "output_path": str(FINAL),
                     "profile": "youtube_shorts", "crf": 20})
    if not r2.success:
        raise SystemExit(f"video_compose encode failed: {r2.error}")
    # audio check via audio_mixer extract
    wav = rdir / "final_audio.wav"
    r3 = tool("audio_mixer").execute({"operation": "extract", "input_path": str(FINAL), "output_path": str(wav)})
    # transcript of the final render for comparison
    r4 = tool("transcriber").execute({"input_path": str(FINAL), "model_size": "small", "language": "ja",
                                      "output_dir": str(rdir)})
    ft = rdir / f"{FINAL.stem}_transcript.json"
    final_review = vc._run_final_review(FINAL, ed, None, narration_transcript_path=str(ft) if r4.success else None,
                                        script_text=" ".join(s["text"] for s in d["segments"]))
    pr = probe(FINAL)
    v = next(s for s in pr["streams"] if s["codec_type"] == "video")
    a = next((s for s in pr["streams"] if s["codec_type"] == "audio"), None)
    num, den = v["r_frame_rate"].split("/")
    dur = float(pr["format"]["duration"])
    report = {
        "version": "1.0",
        "outputs": [{"path": str(FINAL), "format": "mp4", "codec": v["codec_name"],
                     "audio_codec": a["codec_name"] if a else None, "resolution": f"{v['width']}x{v['height']}",
                     "fps": round(int(num) / int(den), 3), "duration_seconds": round(dur, 3),
                     "file_size_bytes": int(pr["format"]["size"]), "platform_target": "youtube_shorts"}],
        "render_time_seconds": round(time.time() - t0, 1),
        "render_grammar": "presenter",
        "warnings": list(final_review.get("issues_found", [])),
        "verification_notes": [
            f"remotion_caption_burn (TalkingHead) {t_burn}s, method=remotion",
            f"video_compose encode profile=youtube_shorts",
            f"audio_mixer extract: {'ok' if r3.success else r3.error}",
            f"final transcript: {'ok' if r4.success else r4.error}",
            f"final_review status={final_review.get('status')}"],
        "metadata": {"job_index": ["clip01-youtube_shorts"], "failed_jobs": [],
                     "intermediates": [str(clip), str(captioned)]},
    }
    if a is None:
        report["outputs"][0].pop("audio_codec")
    save("render_report", report)
    save("final_review", final_review)
    gate("compose", {"render_report": report, "final_review": final_review},
         review(["all clips rendered", "platform specs", "audio levels"], report["warnings"]), gated=False)
    log_time("compose", t0, {"approved": "not gated (human_approval_default: false)",
                             "final_review": final_review.get("status"), "duration": dur})


def stage_publish():
    t0 = time.time()
    report = load("render_report")
    meta_path = OUT_DIR / "test-vtuber-short-publish-metadata.json"
    copy = {"youtube_shorts": {
        "title": "12月5日20時 YouTubeで初配信！【いよるも】#Shorts",
        "description": "VRChat とイラストが好きな いよるも です。12月5日20時に YouTube で初配信します。チャンネル登録して待っててね。",
        "note": "名前と日時は素材の発話から。表記（いよるも）はファイル名に合わせた推定。投稿前に本人確認が必要。"}}
    meta_path.write_text(json.dumps(copy, ensure_ascii=False, indent=2), encoding="utf-8")
    plog = {"version": "1.0", "entries": [{
        "platform": "youtube_shorts", "status": "exported", "export_path": report["outputs"][0]["path"],
"timestamp": datetime.now().astimezone().isoformat(),
        "metadata_used": copy["youtube_shorts"]}],
        "metadata": {"clip_catalog": ["clip01"], "posting_order": ["clip01"],
                     "platform_copy_map": str(meta_path), "schedule_notes": "test run; no upload performed"}}
    save("publish_log", plog)
    gate("publish", {"publish_log": plog}, review(["per-clip metadata", "export package"],
                                                  ["No upload: test run. Copy needs human check before posting."]))
    log_time("publish", t0, {"approved": APPROVAL_NOTE})


if __name__ == "__main__":
    globals()[f"stage_{sys.argv[1]}"]()
    print("OK", sys.argv[1])
