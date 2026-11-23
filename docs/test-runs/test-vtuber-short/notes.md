# test-vtuber-short 作業メモ

- 実施: 2026-11-23 14:08〜14:37（約29分）　担当: あわ（Claude Code）
- 依頼: むぎ「③ OpenMontage で VTuber の縦型ショートを1本作るテスト」
- 対象: `C:\Users\dubia\work\shared-memory\OpenMontage`
- ブランチ: `lane/11-order-check` から `lane/test-vtuber-short` を作成（未コミットの5ファイルは触っていない）
- 出力: `C:\Users\dubia\work\shared-memory\openmontage-output\test-vtuber-short.mp4`（32.6秒、1080x1920、30fps、h264/aac）

## 0. 最初の確認（フルパス）

Git Bash で実行。どちらも終了コード 0。

```
$ /c/Users/dubia/AppData/Local/Microsoft/WinGet/Links/ffmpeg.exe -version
ffmpeg version 9.1-full_build-www.gyan.dev Copyright (c) 2000-2026 the FFmpeg developers
built with gcc 16.2.0 (Rev6, Built by MSYS2 project)
configuration: （省略。--enable-libx264 --enable-whisper などを含む）
libavutil      61. 19.100 / 61. 19.100
libavcodec     63. 24.100 / 63. 24.100
libavformat    63. 16.100 / 63. 16.100
libavdevice    63.  5.100 / 63.  5.100
libavfilter    12.  8.100 / 12.  8.100
libswscale     10.  5.100 / 10.  5.100
libswresample   7.  6.100 /  7.  6.100

$ /c/Users/dubia/AppData/Local/Microsoft/WinGet/Links/ffprobe.exe -version
ffprobe version 9.1-full_build-www.gyan.dev Copyright (c) 2007-2026 the FFmpeg developers
built with gcc 16.2.0 (Rev6, Built by MSYS2 project)
（以下 ffmpeg と同じ）
```

- `where.exe ffmpeg` は権限の都合で実行できなかった（診断のみの項目なので省略）。OpenMontage のツールは PATH 上の `ffmpeg` / `ffprobe` を呼ぶ。最終動画の検証はフルパスの ffprobe で行った。
- 補足: ルームの権限設定で、複数コマンドをつないだ実行や PowerShell からの exe 実行は承認待ちで弾かれた。1コマンドずつの Bash 実行で進めた。

## 1. 素材の選定

ffprobe（フルパス）と faster-whisper（registry の `transcriber`、model small、ja、CPU int8）で確認。4本とも 1080x1920・音声あり。

| ファイル | 尺 | 音声 | 発話（whisper） | 判断 |
|---|---|---|---|---|
| 1116.mp4 | 39.1秒 | aac 44.1kHz 2ch | 24.2秒、8区間。誤認識が多い | 次点以下 |
| 告知いよるも.mp4 | 33.0秒 | aac 48kHz 2ch | 31.1秒（94%）、4区間 | **採用** |
| VRChat_20261117_043857 (1).mp4 | 34.2秒 | aac 48kHz 2ch | 29.8秒、4区間 | 次点 |
| タイトルなし-2026-11-15 16 41 53(copy).mp4 | 56.6秒 | aac 44.1kHz 2ch | 10分たっても文字起こしが終わらず中止 | 不採用 |

**選んだ理由**: `告知いよるも.mp4` は、33秒のほぼ全部（31.1秒）で本人が話していて、自己紹介 → 初配信の日時 → 当日の内容 → チャンネル登録の呼びかけ、と1本で完結している。尺も youtube_shorts の上限60秒に収まり、元から縦 9:16 なので切り抜きの必要がない。

`output\vtuber-smoke\` の動画は使っていない。

## 2. パイプライン（clip-factory）の流れ

- project: `OpenMontage\projects\test-vtuber-short\`（gitignore 対象）
- 実行スクリプト: `projects\test-vtuber-short\runner\run_stages.py`（registry のツールを呼び、`lib.checkpoint.write_checkpoint` で checkpoint を書く）
- 各 stage の director skill（`skills/pipelines/clip-factory/*-director.md`）を読んでから実行した。
- テンプレートとコンポジションの新規作成はしていない。TalkingHead.tsx・Root.tsx は未変更。

| stage | 使ったツール | 内容 | 所要 |
|---|---|---|---|
| idea | なし | brief と decision_log（d-001〜d-006）を作成 | 0.2秒 |
| script | transcriber（faster-whisper small） | 全文の文字起こし、clip01（0.0〜32.5秒）を選定 | 10.9秒 |
| scene_plan | frame_sampler | 0.5/10/20/31秒のフレームで構図を確認。顔は画面中央、字幕は下で干渉なし | 0.7秒 |
| assets | video_trimmer → audio_enhance（normalize_only）→ subtitle_gen（srt） | clip01_norm.mp4 と subtitles.srt | 2.1秒 |
| edit | なし | render_runtime=remotion、renderer_family=presenter、composition_mode=templated | 0.2秒 |
| compose | remotion_caption_burn（TalkingHead）→ video_compose encode（profile=youtube_shorts）→ audio_mixer extract → transcriber（最終動画の確認） | 最終動画を出力。final_review は pass | 119.9秒（Remotion 86.7秒） |
| publish | なし | publish_log と投稿文の下書き（アップロードはしていない） | 一瞬 |

- 字幕: TalkingHead の CaptionOverlay。`caption_props.wordSeparator=""`（日本語なので語の間に空白を入れない）、1ページ8トークン、文字サイズ64、ハイライト `#22D3EE`。
- 音楽: 足していない（素材の音声のみ）。

## 3. 承認（approval_policy）

`decision_log` の d-001 に `category: "approval_policy"` を残し（テストのため最後まで通す。依頼者むぎの指示）、承認が必要な stage は `awaiting_human` を書いたあと `completed`（human_approved=True）にした。

| stage | 承認ゲート | 承認した内容 |
|---|---|---|
| idea | あり | 素材は告知いよるも.mp4、clip-factory、Remotion（HyperFrames は caption-burn 非対応で不採用）、TalkingHead をそのまま使う templated、youtube_shorts、音楽なし、クリップ1本 |
| script | あり | faster-whisper の文字起こしと clip01（0.0〜32.5秒）の選定。誤認識は直さずに残す |
| scene_plan | あり | 元の 9:16 のまま、切り抜きなし、字幕は下、フックのオーバーレイなし |
| assets | あり | 0〜32.5秒のトリム、音量の正規化、srt 字幕。生成素材が無いので hero sample は省略 |
| edit | なし（manifest で false） | 自動で通過 |
| compose | なし（manifest で false） | 自動で通過 |
| publish | あり | 投稿文の下書きと publish_log。アップロードはしない |

## 4. 止まった所・つまずいた所

1. **faster-whisper が PyAV 19 で動かない**（script より前、素材選びの時点）
   - 内容: `TypeError: open() got an unexpected keyword argument 'metadata_errors'`。faster-whisper 1.2.1 が渡す引数を PyAV 19.0.2 が受け付けない。
   - 対処: av に依存しているのが faster-whisper だけだと確かめてから、`pip install av==15.1.0` に戻した。これで動いた。
2. **文字起こしが進まない**（素材選び）
   - 内容: 2本目（告知いよるも.mp4）で10分以上止まった。`python -X utf8` で起動し直すと11秒で終わった。Windows の文字コード（cp932）まわりが原因だと思われる（たぶん）。以降は全部 `-X utf8` で実行。
   - `タイトルなし-2026-11-15 16 41 53(copy).mp4` は `-X utf8` でも10分で終わらず中止した。原因は未調査。
3. **こちらの書き間違いによるスキーマエラー**（scene_plan、edit、publish）
   - `required_assets` の形、`subtitles.position` の値、`publish_log.visibility` の値がスキーマに合わず、直して再実行した。パイプライン側の問題ではない。
4. **final_review の警告2件**（compose。どちらも誤検知と判断）
   - 「字幕が見つからない」: edit_decisions の字幕を asset ID で指定したため、final_review がファイルを見つけられなかった。12秒地点のフレームで、字幕が焼き込まれているのを目で確認した。
   - 「文字起こしと台本の一致0%」: 空白で単語に分けて比べる仕組みなので、日本語では一致しない。最終動画の文字起こしは元の発話とほぼ同じだった。

## 5. 気づいた点（直していない）

- 字幕の誤認識が残っている（例: 「緊急各地」は「緊急告知」、「ギターを引き渡っちゃおうかな」は「弾いちゃおうかな」だと思われる）。推測では直していない。公開するなら `corrections` で直す必要がある。
- 1ページ8トークンで区切るので、文の切れ目をまたいで表示される所がある（例: 「していますそんな私12月5」）。
- `remotion_caption_burn` は日本語に `wordSeparator` を自動で付けない（タイ語のみ対応）。今回は `caption_props` で渡した。
- 投稿文の名前表記「いよるも」はファイル名からの推定。

## 6. かかった時間

- 合計: 約29分（14:08〜14:37）
- 内訳: 確認と調査 約10分、素材の文字起こし 約13分（止まった分を含む）、stage 実行 約2分半（compose 約2分）、確認と記録 数分
