# Paper Tracker

毎朝 **Top 3 論文** を自動で検索・要約・図示して Web とメールで報告するツールです。

- PubMed + Semantic Scholar から論文を取得
- Gemini AI で日本語要約・メカニズム図・ポイント3つを生成
- 報告済み論文は翌日以降の候補から除外
- GitHub Actions で完全自動実行（**完全無料**）
- iPhone / PC から GitHub Pages でいつでも確認可能

---

## セットアップ手順

### 1. Gemini API キーを取得する

1. [Google AI Studio](https://aistudio.google.com/) を開く
2. 右上の「Get API key」→「Create API key in new project」をクリック
3. 表示されたキーをコピーして保管する

### 2. Gmail アプリパスワードを取得する

1. [Google アカウント設定](https://myaccount.google.com/) → 「セキュリティ」
2. 2段階認証を有効にする（まだの場合）
3. 「アプリパスワード」→ アプリ名を入力（例: `paper-tracker`）→ 生成
4. 表示された 16 桁のパスワードをコピー

### 3. GitHub リポジトリを作成して push する

```bash
cd /Users/sakaiyohei/src/paper-tracker
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/あなたのユーザー名/paper-tracker.git
git push -u origin main
```

### 4. GitHub Secrets を設定する

リポジトリの「Settings」→「Secrets and variables」→「Actions」→「New repository secret」で以下を登録：

| Secret 名 | 値 |
|---|---|
| `GEMINI_API_KEY` | Step 1 で取得したキー |
| `GMAIL_ADDRESS` | 送信元 Gmail アドレス（例: `you@gmail.com`） |
| `GMAIL_APP_PASSWORD` | Step 2 で取得した 16 桁パスワード |
| `NOTIFY_EMAIL` | 受信先メールアドレス |
| `PAGES_URL` | GitHub Pages の URL（後で設定、省略可） |

### 5. GitHub Pages を有効にする

「Settings」→「Pages」→ Source: `Deploy from a branch` → Branch: `main` / `docs` フォルダ → 「Save」

数分後に `https://あなたのユーザー名.github.io/paper-tracker/` で閲覧できます。

### 6. 動作確認（手動実行）

「Actions」タブ → 「Daily Paper Report」→「Run workflow」→「Run workflow」

---

## キーワードの変更方法

[`config.yml`](config.yml) を編集するだけです：

```yaml
keywords:
  - "mitochondrial transfer"
  - "PRP"
  - "platelet rich plasma"   # ← 追加する場合はここに書く
report_hour: 7
top_n: 3
```

---

## ファイル構成

```
paper-tracker/
├── .github/workflows/daily.yml   # GitHub Actions（毎朝自動実行）
├── scripts/
│   ├── run.py                    # メイン処理
│   ├── fetch_papers.py           # PubMed + Semantic Scholar 検索
│   ├── summarize.py              # Gemini AI 要約・図生成
│   ├── generate_site.py          # 静的HTML生成
│   └── send_email.py             # メール送信
├── data/
│   ├── reported.json             # 報告済みDOIリスト（自動更新）
│   └── YYYY-MM-DD.json           # 日付ごとの結果（自動生成）
├── docs/                         # GitHub Pages 配信
│   ├── index.html                # メインページ（自動生成）
│   └── history.html              # 過去の履歴（自動生成）
└── config.yml                    # ★ キーワード・設定はここだけ編集
```
