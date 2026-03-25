# MindMapper System Status

更新日: 2026-03-25

---

## システム構成

```
mindmapper/
├── backend/          FastAPI バックエンド (port 8000)
│   └── app/
│       ├── main.py         REST API エンドポイント
│       ├── llm_agent.py    Gemini 連携 (分析・チャット)
│       ├── persistence.py  データ永続化 (JSON)
│       └── watcher.py      notes/ フォルダ監視 (watchdog)
├── frontend/         Next.js 16 フロントエンド (port 3000)
│   ├── app/
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components/
│   │   ├── MindMap.tsx     メイン UI コンポーネント
│   │   └── IssueNode.tsx   カスタム ReactFlow ノード
│   └── lib/
│       ├── api.ts          バックエンド API クライアント
│       └── utils.ts        ユーティリティ
├── data/
│   ├── mindmap.json        ノード/エッジ永続化ストレージ
│   └── chat_history.json   チャット履歴永続化ストレージ
└── notes/                  Markdown ノート監視ディレクトリ
```

---

## API エンドポイント

| Method | Path                  | 説明                                      |
|--------|-----------------------|-------------------------------------------|
| GET    | `/api/graph`          | グラフ全体取得 (nodes + edges)             |
| POST   | `/api/decision`       | ノードに対応方針を保存                     |
| POST   | `/api/issue`          | 課題ノードを手動追加 **[Bug1 修正済]**     |
| POST   | `/api/analyze`        | テキストを Gemini で分析しノード生成 **[Bug3 修正済]** |
| POST   | `/api/chat`           | Gemini にチャット送信 **[Bug3 修正済]**    |
| GET    | `/api/chat_history`   | チャット履歴全件取得 **[新機能]**           |

---

## バグ修正内容

### Bug1: 課題が追加できない
- **原因**: バックエンドに `POST /api/issue` エンドポイントが存在しなかった
- **修正**:
  - `persistence.py` に `add_manual_node()` 関数を追加
  - `main.py` に `POST /api/issue` エンドポイントを追加
  - フロントエンドの Decision タブに課題追加フォーム (ラベル・カテゴリ・優先度) を追加

### Bug2: Web Speech API が途中で止まる
- **原因**: `recognition.continuous` が未設定 (デフォルト `false`)、`onend` / `onerror` ハンドラなし
- **修正** (`MindMap.tsx`):
  ```ts
  rec.continuous = true;          // 継続モード有効化
  rec.onend = () => {
    if (shouldRestartRef.current) rec.start();  // 自動再起動
  };
  rec.onerror = (event) => {
    if (event.error !== "aborted" && shouldRestartRef.current) {
      setTimeout(() => rec.start(), 1000);      // 1秒後再起動
    }
  };
  ```

### Bug3: Gemini 連携が起動しない
- **原因**: `/api/analyze` と `/api/chat` エンドポイントが未実装だったため `api.ts` の呼び出しが 404 で失敗していた
- **修正**:
  - `llm_agent.py` に `analyze_text()` と `chat()` メソッドを追加
  - `main.py` に `/api/analyze` と `/api/chat` エンドポイントを追加
  - 起動時に `LLMAgent` インスタンスを生成して各エンドポイントで共有

---

## 新機能: LLM チャット履歴検索

- **バックエンド**: `/api/chat` の応答を `data/chat_history.json` に追記保存
- **フロントエンド**:
  - チャット送信時に `localStorage` (key: `mindmap_chat_history`) にも保存
  - 起動時にローカルとバックエンドの履歴をマージ
  - 「履歴」タブでキーワード検索 (質問・回答・ノードラベルを対象)
  - 履歴カードをクリックすると関連課題ノードに遷移

---

## 使用技術

| レイヤ     | 技術                                         |
|-----------|----------------------------------------------|
| Frontend  | Next.js 16, React 19, ReactFlow, Tailwind CSS 4, TypeScript |
| Backend   | FastAPI, Pydantic, uvicorn                   |
| AI        | Google Gemini `gemini-3-flash-preview`       |
| 音声入力  | Web Speech API (SpeechRecognition, `ja-JP`)  |
| ファイル監視 | watchdog                                   |
| データ保存 | JSON (mindmap.json, chat_history.json), localStorage |

---

## 起動方法

```bash
# バックエンド
cd mindmapper/backend
pip install -r requirements.txt
GEMINI_API_KEY=xxx uvicorn app.main:app --reload --port 8000

# フロントエンド
cd mindmapper/frontend
npm install
npm run dev   # → http://localhost:3000
```
