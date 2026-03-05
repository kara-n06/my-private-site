# My Private Site

Google Drive をコンテンツ管理に使い、Cloudflare Pages でプライベート配信する静的サイト。

## アーキテクチャ

```
Google Drive → Apps Script (5分間隔) → GitHub Actions → Vite Build → Cloudflare Pages
                                                                         + Access (認証)
```

## セットアップ

### 1. GCP サービスアカウント

1. [GCP Console](https://console.cloud.google.com/) でプロジェクトを作成
2. 「APIとサービス」→ Google Drive API を有効化
3. 「認証情報」→ サービスアカウントを作成
4. サービスアカウントの鍵（JSON）をダウンロード
5. Google Drive でコンテンツフォルダをサービスアカウントのメールアドレスに **閲覧者** として共有

### 2. GitHub リポジトリ

1. このリポジトリを GitHub に push
2. Settings → Secrets and variables → Actions で以下を設定:

| Secret | 値 |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_KEY` | サービスアカウント JSON 鍵の **中身全体** |
| `DRIVE_FOLDER_ID` | Drive コンテンツフォルダの ID（URL の `/folders/` 以降） |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API トークン（Pages 編集権限） |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare アカウント ID |

### 3. Cloudflare Pages

1. Cloudflare Dashboard → Workers & Pages → Create application → Pages
2. 「Direct Upload」でプロジェクト作成、名前を `my-private-site` に設定
3. 初回は空の dist/ をアップロード（以降は GitHub Actions が自動デプロイ）

### 4. Cloudflare Access（プライベート化）

1. Cloudflare Dashboard → Zero Trust → Access → Applications
2. 「Add an application」→ Self-hosted
3. Application domain: `my-private-site.pages.dev`
4. Policy: Allow → Include → Email: `your@email.com`

### 5. Google Apps Script

1. [script.google.com](https://script.google.com) で新規プロジェクト作成
2. `scripts/trigger.gs` の内容を貼り付け
3. `GITHUB_REPO` と `DRIVE_FOLDER_ID` を書き換え
4. プロジェクトの設定 → スクリプトプロパティ → `GITHUB_TOKEN` を追加
   - GitHub → Settings → Developer settings → Fine-grained tokens
   - Repository: このリポジトリのみ
   - Permissions: Actions (Read and Write)
5. トリガー → `checkForChangesAndDeploy` → 時間主導型 → 5分おき

## 使い方

### コンテンツ追加

1. Google Drive のフォルダにファイルを追加・編集
2. 5分以内に自動デプロイされる
3. 手動デプロイ: GitHub → Actions → Run workflow

### Google Drive フォルダ構成

```
📁 my-site-content/
├── 📁 pages/         ← HTML ページ
├── 📁 components/    ← React コンポーネント（.tsx）
├── 📁 assets/        ← 画像、CSS 等
└── 📄 site-config.json
```

### 画像の埋め込み

1. `assets/images/` に画像を配置
2. HTML で参照: `<img src="/assets/images/photo.jpg" alt="..." />`

## ローカル開発

```bash
npm install
npm run dev     # http://localhost:5173
npm run build   # dist/ に出力
```

## 費用

**¥0/月** — 全サービスの無料枠内で運用可能。
