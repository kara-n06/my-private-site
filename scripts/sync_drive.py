"""Google Drive からコンテンツを src/content/ に同期する.

Usage:
    GOOGLE_SERVICE_ACCOUNT_KEY='...' DRIVE_FOLDER_ID='...' python scripts/sync_drive.py

CI 環境（GitHub Actions）で実行される前提。
サービスアカウントの JSON 鍵は環境変数から取得する。
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
CONTENT_DIR = Path("src/content")

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


def download_folder(service, folder_id: str, local_path: Path) -> int:
    """フォルダを再帰的にダウンロードし、同期したファイル数を返す."""
    local_path.mkdir(parents=True, exist_ok=True)
    count = 0

    for item in list_files(service, folder_id):
        mime = item["mimeType"]
        name: str = item["name"]
        item_path = local_path / name

        if mime == "application/vnd.google-apps.folder":
            count += download_folder(service, item["id"], item_path)

        elif mime in EXPORT_MAP:
            export_mime, ext = EXPORT_MAP[mime]
            dest = item_path.with_suffix(ext)
            _export_file(service, item["id"], export_mime, dest)
            count += 1

        elif mime not in SKIP_MIMETYPES:
            _download_file(service, item["id"], item_path)
            count += 1

    return count


def _export_file(service, file_id: str, mime: str, dest: Path) -> None:
    """Google Workspace ファイルを指定 MIME type でエクスポート."""
    data = service.files().export_media(fileId=file_id, mimeType=mime).execute()
    dest.write_bytes(data)
    print(f"  exported  : {dest}")


def _download_file(service, file_id: str, dest: Path) -> None:
    """通常ファイル（画像、HTML、CSS、TSX 等）をダウンロード."""
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    dest.write_bytes(buf.getvalue())
    print(f"  downloaded: {dest}")


def main() -> None:
    folder_id = os.environ.get("DRIVE_FOLDER_ID")
    if not folder_id:
        print("ERROR: DRIVE_FOLDER_ID is not set", file=sys.stderr)
        sys.exit(1)

    service = get_drive_service()

    # クリーンスタート（.gitkeep 以外を削除）
    if CONTENT_DIR.exists():
        shutil.rmtree(CONTENT_DIR)

    print(f"Syncing from Google Drive (folder: {folder_id}) ...")
    count = download_folder(service, folder_id, CONTENT_DIR)
    print(f"Sync complete: {count} file(s)")


if __name__ == "__main__":
    main()
