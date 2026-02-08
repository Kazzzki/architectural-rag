# 🏗 建築意匠ナレッジRAGシステム（Webアプリ版）

建築PM/CM業務向けナレッジ検索・回答生成Webアプリケーション。

## 技術スタック

- **Backend**: FastAPI + ChromaDB + Gemini 3.0 Flash
- **Frontend**: Next.js 14 + TypeScript + Tailwind CSS

## セットアップ

### 1. 環境変数

```bash
export GEMINI_API_KEY="your-api-key"
```

### 2. バックエンド起動

```bash
cd architectural_rag
pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

### 3. フロントエンド起動

```bash
cd frontend
npm install
npm run dev
```

### 4. アクセス

- フロントエンド: http://localhost:3000
- API: http://localhost:8000/docs

## ファイル構成

```
architectural_rag/
├── server.py         # FastAPI バックエンド
├── config.py         # 設定
├── indexer.py        # インデックス作成
├── retriever.py      # ベクトル検索
├── generator.py      # 回答生成
├── requirements.txt  # Python依存
└── frontend/         # Next.js フロントエンド
    ├── app/
    │   ├── page.tsx
    │   ├── layout.tsx
    │   └── globals.css
    └── package.json
```

## API エンドポイント

| Method | Path | 説明 |
|--------|------|------|
| POST | /api/chat | 質問→回答 |
| POST | /api/upload | ファイルアップロード |
| POST | /api/index | インデックス再構築 |
| GET | /api/stats | DB統計 |
