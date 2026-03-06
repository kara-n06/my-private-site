"""Google Drive からコンテンツを同期する.

ファイル種別に応じて同期先を振り分ける:
  - .tsx / .jsx        → src/content/   （Vite がコンパイル）
  - .html / .css / 画像 → public/        （Vite がそのまま dist/ にコピー）

Usage:
    GOOGLE_SERVICE_ACCOUNT_KEY='...' DRIVE_FOLDER_ID='...' python scripts/sync_drive.py

CI 環境（GitHub Actions）で実行される前提。
サービスアカウントの JSON 鍵は環境変数から取得する。
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# 同期先ディレクトリ
STATIC_DIR = Path("public")       # HTML, CSS, 画像等 → そのまま配信
COMPILED_DIR = Path("src/content")  # TSX, JSX → Vite がコンパイル

# Vite コンパイルが必要な拡張子
COMPILABLE_EXTENSIONS: set[str] = {".tsx", ".jsx", ".ts"}

# Google Workspace ファイル → エクスポート形式
EXPORT_MAP: dict[str, tuple[str, str]] = {
    "application/vnd.google-apps.document": ("text/html", ".html"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", ".csv"),
}

# 同期スキップ対象の MIME types
SKIP_MIMETYPES: set[str] = {
    "application/vnd.google-apps.folder",
    "application/vnd.google-apps.shortcut",
    "application/vnd.google-apps.form",
    "application/vnd.google-apps.map",
}


def get_drive_service():
    """サービスアカウント認証で Drive API v3 クライアントを生成."""
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY")
    if not raw:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT_KEY is not set", file=sys.stderr)
        sys.exit(1)

    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw),
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=creds)


def _resolve_dest(filename: str, rel_folder: Path) -> Path:
    """ファイル名の拡張子に応じて同期先を決定する.

    Args:
        filename: ファイル名（拡張子を含む）
        rel_folder: Drive フォルダルートからの相対パス

    Returns:
        書き込み先の絶対パス
    """
    ext = Path(filename).suffix.lower()
    if ext in COMPILABLE_EXTENSIONS:
        return COMPILED_DIR / rel_folder / filename
    return STATIC_DIR / rel_folder / filename


def list_files(service, folder_id: str) -> list[dict]:
    """指定フォルダ直下のファイル一覧を取得（ページネーション対応）."""
    items: list[dict] = []
    page_token: str | None = None

    while True:
        resp = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, size)",
                pageSize=200,
                pageToken=page_token,
            )
            .execute()
        )
        items.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return items


def download_folder(
    service,
    folder_id: str,
    rel_folder: Path,
    synced: list[Path] | None = None,
) -> int:
    """フォルダを再帰的にダウンロードし、同期したファイル数を返す.

    Args:
        service: Drive API クライアント
        folder_id: Drive フォルダ ID
        rel_folder: Drive ルートからの相対パス（振り分けに使用）
        synced: 同期したファイルパスを蓄積するリスト
    """
    if synced is None:
        synced = []
    count = 0

    for item in list_files(service, folder_id):
        mime = item["mimeType"]
        name: str = item["name"]

        if mime == "application/vnd.google-apps.folder":
            count += download_folder(service, item["id"], rel_folder / name, synced)

        elif mime in EXPORT_MAP:
            export_mime, ext = EXPORT_MAP[mime]
            exported_name = Path(name).with_suffix(ext).name
            dest = _resolve_dest(exported_name, rel_folder)
            dest.parent.mkdir(parents=True, exist_ok=True)
            exported_files = _export_file(service, item["id"], export_mime, dest)
            synced.extend(exported_files)
            count += 1

        elif mime not in SKIP_MIMETYPES:
            dest = _resolve_dest(name, rel_folder)
            dest.parent.mkdir(parents=True, exist_ok=True)
            _download_file(service, item["id"], dest)
            synced.append(dest)
            count += 1

            # Inject navigation script if the downloaded file is a standalone HTML page
            if dest.suffix.lower() == ".html":
                _inject_navigation(dest)

    return count


def _export_file(service, file_id: str, mime: str, dest: Path) -> list[Path]:
    """Google Workspace ファイルを指定 MIME type でエクスポート."""
    data = service.files().export_media(fileId=file_id, mimeType=mime).execute()
    created_files = [dest]

    if mime == "text/html":
        # Google Docs export as text/html returns a ZIP archive
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            html_files = [f for f in z.namelist() if f.endswith(".html")]
            if html_files:
                html_filename = html_files[0]
                html_content = z.read(html_filename).decode("utf-8")

                # Setup image directory for this specific document
                images_dir_name = f"{dest.stem}_images"
                images_dest_dir = dest.parent / images_dir_name

                # Extract images and rewrite paths
                has_images = False
                for file_in_zip in z.namelist():
                    if file_in_zip.startswith("images/") and len(file_in_zip) > 7:
                        has_images = True
                        images_dest_dir.mkdir(parents=True, exist_ok=True)
                        img_data = z.read(file_in_zip)
                        img_name = Path(file_in_zip).name
                        img_dest = images_dest_dir / img_name
                        img_dest.write_bytes(img_data)
                        created_files.append(img_dest)

                if has_images:
                    # Rewrite src="images/..." to src="docname_images/..."
                    html_content = re.sub(r'(src=["\'])images/', rf'\1{images_dir_name}/', html_content)

                dest.write_text(html_content, encoding="utf-8")
                print(f"  exported (extracted from zip) → {dest}")
            else:
                dest.write_bytes(data)
                print(f"  exported → {dest}")
    else:
        dest.write_bytes(data)
        print(f"  exported  → {dest}")

    return created_files


def _download_file(service, file_id: str, dest: Path) -> None:
    """通常ファイル（画像、HTML、CSS、TSX 等）をダウンロード."""
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    dest.write_bytes(buf.getvalue())
    print(f"  downloaded → {dest}")


def _inject_navigation(html_path: Path) -> None:
    """スタンドアロンの HTML ページにナビゲーション用の JS を注入する."""
    try:
        content = html_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return  # バイナリ等の場合はスキップ

    nav_script = """
<script>
document.addEventListener('DOMContentLoaded', function() {
    fetch('/pages.json')
      .then(res => res.json())
      .then(pages => {
          const nav = document.createElement('div');
          nav.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 50px; background: #f8f9fa; border-bottom: 1px solid #ddd; padding: 10px 20px; z-index: 99999; display: flex; gap: 15px; overflow-x: auto; font-family: sans-serif; box-sizing: border-box;';
          let html = '<a href="/" style="color: #000; font-weight: bold; text-decoration: none;">🏠 Home</a>';
          pages.forEach(p => {
              html += `<a href="${p.path}" style="color: #0066cc; text-decoration: none;">${p.title}</a>`;
          });
          nav.innerHTML = html;
          document.body.prepend(nav);
          document.body.style.marginTop = '50px';
      })
      .catch(e => console.error('Failed to load navigation', e));
});
</script>
"""
    if "</body>" in content:
        content = content.replace("</body>", f"{nav_script}\n</body>")
    else:
        content += nav_script
    html_path.write_text(content, encoding="utf-8")


def _clean_synced_content() -> None:
    """前回同期分をクリア（リポジトリ側のファイルは残す）.

    マニフェストファイルに前回同期したパスを記録し、
    次回同期時にそのファイルだけを削除する。
    """
    manifest = Path(".drive-sync-manifest")

    # src/content/ は Drive 同期専用なので全削除して問題ない
    if COMPILED_DIR.exists():
        shutil.rmtree(COMPILED_DIR)
    COMPILED_DIR.mkdir(parents=True, exist_ok=True)

    # public/ は _redirects 等リポジトリのファイルもあるので
    # マニフェストに記録された Drive 由来ファイルのみ削除
    if manifest.exists():
        for line in manifest.read_text().splitlines():
            p = Path(line.strip())
            if p.exists() and p.is_file():
                p.unlink()
        # 空ディレクトリを掃除
        for dirpath in sorted(STATIC_DIR.rglob("*"), reverse=True):
            if dirpath.is_dir() and not any(dirpath.iterdir()):
                dirpath.rmdir()

    manifest.unlink(missing_ok=True)


def _record_manifest(synced_files: list[Path]) -> None:
    """同期したファイルのパスをマニフェストに記録."""
    manifest = Path(".drive-sync-manifest")
    manifest.write_text("\n".join(str(p) for p in synced_files) + "\n")


def _record_pages_index(synced_files: list[Path]) -> None:
    """フロントエンドのナビゲーション用に index を生成."""
    pages = []

    for p in synced_files:
        if p.suffix == ".html" and "public" in p.parts:
            # public/ 配下のHTMLファイル
            idx = p.parts.index("public")
            rel_parts = p.parts[idx+1:]
            rel_path = "/".join(rel_parts)
            pages.append({"title": p.stem, "path": f"/{rel_path}"})
        elif p.suffix in COMPILABLE_EXTENSIONS and "src" in p.parts and "content" in p.parts:
            # src/content/ 配下のコンパイル対象ファイル
            idx = p.parts.index("content")
            rel_parts = p.parts[idx+1:]
            rel_path = "/".join(rel_parts)
            rel_path = rel_path.rsplit(".", 1)[0].lower()
            pages.append({"title": p.stem, "path": f"/{rel_path}"})

    index_path = STATIC_DIR / "pages.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Index generated: {index_path} ({len(pages)} pages)")


def main() -> None:
    folder_id = os.environ.get("DRIVE_FOLDER_ID")
    if not folder_id:
        print("ERROR: DRIVE_FOLDER_ID is not set", file=sys.stderr)
        sys.exit(1)

    service = get_drive_service()

    _clean_synced_content()

    print(f"Syncing from Google Drive (folder: {folder_id}) ...")
    print(f"  Static files  → {STATIC_DIR}/")
    print(f"  Compiled files → {COMPILED_DIR}/")

    synced: list[Path] = []
    count = download_folder(service, folder_id, Path(""), synced)
    _record_manifest(synced)
    _record_pages_index(synced)

    print(f"Sync complete: {count} file(s)")


if __name__ == "__main__":
    main()
