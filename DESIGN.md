# Design System — 建築PM/CMナレッジRAG

## Product Context
- **What this is:** 建築PM/CM業務向けナレッジ検索・タスク管理・会議録・因果グラフ統合Webアプリ
- **Who it's for:** 建設プロジェクトのPM/CMr（プロフェッショナル）
- **Space/industry:** 建設業界のプロジェクトマネジメント
- **Project type:** 業務用Webアプリ（ダッシュボード + データ管理）

## Aesthetic Direction
- **Direction:** Industrial/Utilitarian with soft edges
- **Decoration level:** Minimal — データが主役、装飾ではなく構造で整理
- **Mood:** 信頼できるプロフェッショナルツール。丸みのあるUIで親しみやすさを加える
- **Key principle:** パッと見てパッと判断できる情報密度。ただし角を丸くして圧迫感を減らす

## Typography
- **Display/Hero:** Geist (700) — クリーンで現代的、Vercel製でNext.jsと親和性が高い
- **Body:** Geist (400/500) — 読みやすさとコンパクトさを両立
- **UI/Labels:** Geist (500/600) — ボタンやラベルに使用
- **Data/Tables:** Geist Mono (400) — 日付、ID、数値、期限の表示に必ず使用。tabular-nums対応で「精密なツール」感を演出
- **Code:** Geist Mono
- **Loading:** Google Fonts `family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500`
- **Scale:**
  - xs: 11px — メタ情報、カウンター
  - sm: 12px — ラベル、セクションヘッダー
  - base: 13-14px — 本文、タスクタイトル
  - lg: 15px — ページタイトル
  - xl: 18px — セクション見出し
  - 2xl: 24-28px — ヒーロー見出し
- **Blacklisted:** Inter, Roboto, Arial, Helvetica, Open Sans, Poppins（使用禁止）

## Color
- **Approach:** Restrained — 1アクセント + ニュートラル。色は意味がある時だけ
- **Accent:** `#2563eb` (Blue-600) — 図面・設計書の青色リンクと親和。インタラクティブ要素に使用
- **Accent Light:** `#3b82f6` (Blue-500) — hover時
- **Accent Background:** `rgba(37, 99, 235, 0.06)` — 選択状態の背景
- **Neutrals (Slate系):**
  - 50: `#f8fafc` — ページ背景
  - 100: `#f1f5f9` — サーフェスhover、セカンダリ背景
  - 200: `#e2e8f0` — ボーダー
  - 400: `#94a3b8` — ミュートテキスト
  - 600: `#475569` — セカンダリテキスト
  - 800: `#1e293b` — ダークサーフェス
  - 900: `#0f172a` — プライマリテキスト、ヘッダー背景
- **Semantic:**
  - Success: `#16a34a` / bg: `rgba(22, 163, 74, 0.08)` — 完了、正常
  - Warning: `#d97706` / bg: `rgba(217, 119, 6, 0.08)` — 注意、本日期限
  - Error: `#dc2626` / bg: `rgba(220, 38, 38, 0.08)` — 期限超過、エラー
- **Deprecated:** `#6d28d9` (紫) — 建設業務に馴染みがないため廃止
- **Dark mode strategy:** サーフェスを暗転、彩度を10-20%下げ、ボーダーをSlate 700に

## Spacing
- **Base unit:** 4px
- **Density:** コンパクト — 業務データを効率よく表示
- **Scale:** 2xs(2) xs(4) sm(8) md(12) lg(16) xl(24) 2xl(32) 3xl(48) 4xl(64)

## Layout
- **Approach:** Grid-disciplined — 整列されたカラムレイアウト
- **Max content width:** 1280px
- **Grid:** 12カラム (デスクトップ)、1カラム (モバイル)
- **Sidebar:** 必要時のみ表示（TaskDetailPanel等）

## Border Radius
- **Approach:** Rounded/Soft — 丸みのある柔らかい印象
- **Scale:**
  - sm: `6px` — アラート、テーブルセル
  - md: `10px` — カード、タスクカード、入力フィールド
  - lg: `16px` — モーダル、パネル、コンテナ
  - full: `9999px` — バッジ(pill)、ボタン、タブ、チェックボックス、アサイニータグ
- **Rule:** インタラクティブ要素（ボタン、バッジ、タブ）はfull。コンテナ（カード、モーダル）はlg。

## Motion
- **Approach:** Minimal-functional — 理解を助けるトランジションのみ
- **Easing:** enter: ease-out, exit: ease-in, move: ease-in-out
- **Duration:** micro: 100ms, short: 150ms, medium: 250ms
- **Usage:** ホバー状態の変化、パネルの開閉、ドラッグ&ドロップのフィードバック

## Component Patterns
- **Buttons:** pill型 (border-radius: full)。Primary=青背景白文字、Secondary=グレー背景、Ghost=透明
- **Badges/Tags:** pill型。優先度はセマンティックカラー背景 (H=赤, M=オレンジ, L=グレー)
- **Task Cards:** md角丸、1pxボーダー、hover時にアクセントボーダー+シャドウ
- **View Tabs:** pill型セグメントコントロール（背景グレー、アクティブ=白）
- **Checkboxes:** 丸型 (border-radius: full)
- **Data Display:** Geist Monoで日付・ID・数値を表示。必ずモノスペースにする
- **Headers:** ダークスレート(#0f172a)背景、白テキスト、青アクセントアイコン

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-05 | Initial design system created | /design-consultation based on product context analysis |
| 2026-04-05 | Industrial/Utilitarian with soft edges | PM/CMプロが信頼できるツール + 丸みで親しみやすさ |
| 2026-04-05 | Geist + Geist Mono | Inter排除。Vercel製でNext.js親和性、Interよりシャープ |
| 2026-04-05 | Blue-600 accent, purple deprecated | 建設業の図面青と親和。紫は業界に馴染みなし |
| 2026-04-05 | Rounded corners (pill buttons, 10-16px cards) | シャープすぎる印象を避け、柔らかい専門ツール感 |
