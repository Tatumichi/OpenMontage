# OpenMontageでmoviemakerの字幕を使う

Claude CodeまたはCodexに、素材動画、moviemakerの `data.json`、残したい場面、希望の尺をまとめて渡します。OpenMontageではエージェントがパイプラインを選び、素材確認から書き出しまで進めます。長い配信から複数の切り抜きを作る入口は `clip-factory` です。

> この配信素材を縦型のショートに編集して。字幕は添付のmoviemakerのdata.jsonを使って。顔が隠れない位置に字幕を置き、MP4と字幕SRTを出力して。ローカルで書き出し、字幕と音声を確認して。

## 字幕の取り込み

OpenMontageのルートで以下のPythonコードを実行できます。字幕変換にはPython標準ライブラリを使います。入出力パスは手元のファイルに合わせてください。

```python
from pathlib import Path
import json

from tools.subtitle.subtitle_gen import SubtitleGen

data = json.loads(Path("output/vtuber-smoke/data.json").read_text(encoding="utf-8-sig"))
result = SubtitleGen().execute({
    "moviemaker_cuts": data["cuts"],
    "format": "srt",
    "output_path": "output/vtuber-smoke/captions.srt",
})
if not result.success:
    raise SystemExit(result.error)
print(result.data)
```

各カットの `start` と `end` は出力動画上の秒数です。切り出し後の時刻が異なる場合は、出力を0秒として調整してください。`lines` の1要素が字幕の1行になり、字幕のないカットは飛ばします。SRT、VTT、JSONに対応します。字幕を焼き込む場合はSRTを使用できます。単語単位の強調には、単語時刻付きの `segments` を使います。

## 統合できる機能

| moviemakerの機能 | OpenMontageでの使い方 |
| --- | --- |
| カット字幕 | `subtitle_gen` に組み込み済み。確定した時刻と改行を保持 |
| 文字起こし・見どころ候補・カット割り | `clip-factory` の候補選定やシーン計画に接続する候補。話者や素材時刻の対応を確認する |
| 顔を基準にしたリフレーム・効果音・スタンプ | 編集工程で再利用する候補。素材パス、座標、レイヤー順の対応を確認する |
| テンプレート・トランジション・キーフレーム | 描画とテンプレートの宣言に依存。デザイン調査後に扱う |

## 動作確認とデザイン調査

`output/vtuber-smoke/` に、まいの既存立ち絵を使った8秒・720×1280の無音MP4、3区間分の字幕、確認フレームを出力しました。字幕変換とローカルFFmpegでの焼き込みを検証しました。長尺素材の自動抽出、Remotionでの合成、Backlotの操作は実機確認が残っています。

YouTube公式の切り抜きガイドでは、9:16、単体で伝わる構成、音声オフでも内容が伝わる字幕を紹介しています。冒頭で状況を示し、顔と字幕が重ならない配置を試しました。VTuberショート固有の流行は、複数の実例を比べて字幕の位置・強調・画角の切り替えを確認する段階です。[YouTube公式の切り抜きガイド](https://blog.youtube/creator-and-artist-stories/transitioning-your-long-form-content-to-youtube-shorts/)・[2026年のShorts画面アップデート](https://blog.youtube/news-and-events/youtube-shorts-experience-updates-features/)