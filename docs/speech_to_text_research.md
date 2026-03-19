# 音声文字起こし（Speech-to-Text）LLMモデル調査

**調査日**: 2026年3月19日

---

## 調査概要

建築意匠ナレッジRAGシステムの `/api/transcribe` エンドポイントで使用する音声文字起こしモデルの選定のため、2026年時点の最新モデルを調査した。

---

## 最新モデル比較（2026年3月時点）

### 精度ランキング（AA-WER: 低いほど高精度）

| 順位 | モデル | プロバイダー | AA-WER | 特徴 |
|------|--------|------------|--------|------|
| 1 | **Scribe v2** | ElevenLabs | 2.3% | 商用最高精度 |
| 2 | **Gemini 3 Pro** | Google | 2.9% | 話者識別・要約まで対応 |
| 3 | **Voxtral Small** | Mistral | 3.0% | オープンウェイト最高精度 |
| 4 | **Gemini 2.5 Pro** | Google | 3.1% | マルチモーダル対応 |
| 5 | **Gemini 3 Flash** | Google | 3.1% | **現システム採用・高速・低コスト** |
| 6 | **NVIDIA Canary Qwen 2.5B** | NVIDIA | 5.63% | HuggingFace OSSランキング1位 |
| 7 | **Whisper Large V3 Turbo** | OpenAI | ~6% | ローカル運用可能、OSSスタンダード |

---

## 主要モデル詳細

### Google Gemini 3 Flash（現システム採用）
- **モデルID**: `gemini-3-flash-preview`
- **WER**: 3.1%（ランキング4-5位）
- **特徴**:
  - 高速・低コスト
  - 日本語対応（高精度）
  - 話者識別機能
  - 文字起こし後の要約・分析も可能
  - マルチモーダル（音声・画像・テキスト）
- **採用理由**: 既存システムとの統合性が高く、高速かつ十分な精度を持つ。

### OpenAI gpt-4o-transcribe
- **特徴**: WER低い、100言語対応、320msレイテンシ
- **不採用理由**: 本システムはGemini API中心のため、別APIキーが必要

### NVIDIA Canary Qwen 2.5B
- **特徴**: OSSランキング1位（WER 5.63%）、ローカル運用可能
- **アーキテクチャ**: SALM（Speech-Augmented Language Model）- ASR＋LLMを統合
- **不採用理由**: GPU環境が必要、Gemini比でWERが劣る

### Whisper Large V3 / Turbo（OpenAI）
- **特徴**: ローカル運用可能、99言語対応、OSSスタンダード
- **Turbo版**: 809Mパラメータ、Large V3比6倍速
- **不採用理由**: Geminiより精度が低い、APIコール方式と異なる

---

## 現システムの設定

```python
# config.py
GEMINI_MODEL_TRANSCRIPTION = os.getenv("GEMINI_MODEL_TRANSCRIPTION", "gemini-3-flash-preview")
```

環境変数 `GEMINI_MODEL_TRANSCRIPTION` を設定することで、将来的なモデルアップグレードが容易。

---

## 将来的なアップグレード候補

より高精度が必要な場合は以下への移行を検討：

1. **Gemini 3 Pro** (`gemini-3-pro-preview`) — WER 2.9%、高精度・低速
2. **ElevenLabs Scribe v2** — WER 2.3%、最高精度（別API統合が必要）

---

## 参考文献

- [Best Speech Recognition Models 2026 | AI Portal X](https://aiportalx.com/blog/best-speech-recognition-models-2026-whisper-v3-gemini-audio)
- [Best open source STT model 2026 | Northflank](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
- [Speech to Text Leaderboard | Artificial Analysis](https://artificialanalysis.ai/speech-to-text)
- [【2026年最新】LLM文字起こしの精度を上げる方法 | AX](https://a-x.inc/blog/llm-transcription/)
