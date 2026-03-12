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

import html
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

# ナビゲーションに表示するリンクの最大数（超えたら "More ▾" に収納）
NAV_VISIBLE_LIMIT = 5


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
    """ファイル名の拡張子に応じて同期先を決定する."""
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
    """フォルダを再帰的にダウンロードし、同期したファイル数を返す."""
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

            if dest.suffix.lower() == ".html":
                _inject_navigation(dest)

    return count


def _export_file(service, file_id: str, mime: str, dest: Path) -> list[Path]:
    """Google Workspace ファイルを指定 MIME type でエクスポート."""
    data = service.files().export_media(fileId=file_id, mimeType=mime).execute()
    created_files = [dest]

    if mime == "text/html":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            html_files = [f for f in z.namelist() if f.endswith(".html")]
            if html_files:
                html_content = z.read(html_files[0]).decode("utf-8")

                images_dir_name = f"{dest.stem}_images"
                images_dest_dir = dest.parent / images_dir_name

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
    """スタンドアロンの HTML ページにナビゲーション用の CSS + JS を注入する.

    デザイントークンは global.css と同期させること。
    NAV_VISIBLE_LIMIT を超えたページは "More ▾" ドロップダウンに収納する。
    """
    try:
        content = html_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return

    nav_style = """
<style>
  /* ── Design Tokens (sync with global.css) ── */
  :root {
    --nav-bg:       rgba(11, 16, 23, 0.92);
    --nav-border:   #162030;
    --nav-height:   52px;
    --accent:       #0ea5e9;
    --accent-lo:    rgba(14, 165, 233, 0.09);
    --accent-md:    rgba(14, 165, 233, 0.18);
    --border-hi:    rgba(14, 165, 233, 0.35);
    --surf2:        #0f1825;
    --txt:          #dde6f0;
    --txt2:         #7a9bb5;
    --txt3:         #3d5a73;
    --radius:       6px;
    --radius-lg:    10px;
    --shadow-md:    0 8px 24px rgba(0,0,0,0.6);
    --shadow-glow:  0 0 20px rgba(14, 165, 233, 0.15);
    --font-mono:    'IBM Plex Mono', monospace;
    --font-disp:    'Bebas Neue', sans-serif;
    --font-sans:    'IBM Plex Sans', sans-serif;
  }

  /* ── Google Fonts (same subset as global.css) ── */
  @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500&display=swap');

  /* ── Keyframes ── */
  @keyframes _siteNavGlowBlink {
    0%, 100% { opacity: .4; }
    50%       { opacity: 1; }
  }
  @keyframes _siteNavDropIn {
    from { opacity: 0; transform: translateY(-6px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  /* ── Nav shell ── */
  #__site-nav {
    position: fixed;
    top: 0; left: 0;
    width: 100%;
    height: var(--nav-height);
    background: var(--nav-bg);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--nav-border);
    z-index: 99999;
    display: flex;
    align-items: center;
    padding: 0 20px;
    gap: 0;
    box-sizing: border-box;
    font-family: var(--font-sans);
  }

  /* ── Logo ── */
  #__site-nav .sn-logo {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--txt);
    font-family: var(--font-disp);
    font-size: 1.1rem;
    letter-spacing: .1em;
    white-space: nowrap;
    flex-shrink: 0;
    text-decoration: none;
    transition: color .15s ease;
  }
  #__site-nav .sn-logo:hover { color: var(--accent); text-decoration: none; }
  #__site-nav .sn-logo-icon {
    color: var(--accent);
    font-size: 1rem;
    animation: _siteNavGlowBlink 3s ease-in-out infinite;
  }

  /* ── Divider ── */
  #__site-nav .sn-divider {
    width: 1px;
    height: 22px;
    background: var(--nav-border);
    margin: 0 16px;
    flex-shrink: 0;
  }

  /* ── Links container ── */
  #__site-nav .sn-links {
    display: flex;
    align-items: center;
    gap: 4px;
    flex: 1;
    overflow: hidden;
  }

  /* ── Nav button (shared) ── */
  #__site-nav .sn-btn {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 12px;
    border-radius: var(--radius);
    font-size: .8rem;
    font-family: var(--font-mono);
    letter-spacing: .04em;
    color: var(--txt2);
    background: transparent;
    border: none;
    cursor: pointer;
    white-space: nowrap;
    text-decoration: none;
    transition: all .15s ease;
    -webkit-font-smoothing: antialiased;
  }
  #__site-nav .sn-btn:hover {
    color: var(--txt);
    background: var(--accent-lo);
    text-decoration: none;
  }
  #__site-nav .sn-btn.active {
    color: var(--accent);
    background: var(--accent-md);
  }

  /* ── More trigger ── */
  #__site-nav .sn-more-wrap {
    position: relative;
    flex-shrink: 0;
    margin-left: auto;
  }
  #__site-nav .sn-more-btn {
    border: 1px solid var(--nav-border);
  }
  #__site-nav .sn-more-btn:hover,
  #__site-nav .sn-more-btn.open {
    border-color: var(--border-hi);
  }
  #__site-nav .sn-more-btn.active {
    color: var(--accent);
    background: var(--accent-md);
    border-color: var(--border-hi);
  }
  #__site-nav .sn-chevron {
    font-size: .6rem;
    opacity: .6;
  }

  /* ── Dropdown ── */
  #__site-nav .sn-dropdown {
    position: absolute;
    top: calc(100% + 8px);
    right: 0;
    min-width: 200px;
    background: var(--surf2);
    border: 1px solid var(--border-hi);
    border-radius: var(--radius-lg);
    padding: 6px;
    box-shadow: var(--shadow-md), var(--shadow-glow);
    animation: _siteNavDropIn .18s ease both;
    z-index: 200;
    display: none;
  }
  #__site-nav .sn-dropdown.open { display: block; }

  #__site-nav .sn-drop-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-radius: var(--radius);
    font-size: .82rem;
    font-family: var(--font-mono);
    color: var(--txt2);
    text-decoration: none;
    transition: all .12s ease;
    -webkit-font-smoothing: antialiased;
  }
  #__site-nav .sn-drop-item:hover {
    color: var(--txt);
    background: var(--accent-lo);
    text-decoration: none;
  }
  #__site-nav .sn-drop-item.active {
    color: var(--accent);
    background: var(--accent-md);
  }
  #__site-nav .sn-drop-bullet {
    color: var(--accent);
    opacity: .6;
    font-size: .9rem;
  }
</style>
"""

    nav_script = f"""
<script>
(function() {{
  var LIMIT = {NAV_VISIBLE_LIMIT};
  var currentPath = window.location.pathname;

  fetch('/pages.json')
    .then(function(r) {{ return r.json(); }})
    .then(function(pages) {{
      var primary  = pages.slice(0, LIMIT);
      var overflow = pages.slice(LIMIT);

      /* ── Build nav ── */
      var nav = document.createElement('div');
      nav.id = '__site-nav';

      /* Logo */
      var logo = document.createElement('a');
      logo.href = '/';
      logo.className = 'sn-logo';
      logo.innerHTML = '<span class="sn-logo-icon">◈</span><span>HOME</span>';
      nav.appendChild(logo);

      /* Divider */
      var divider = document.createElement('div');
      divider.className = 'sn-divider';
      nav.appendChild(divider);

      /* Links container */
      var links = document.createElement('div');
      links.className = 'sn-links';

      primary.forEach(function(p) {{
        var a = document.createElement('a');
        a.href = p.path;
        a.className = 'sn-btn' + (currentPath === p.path ? ' active' : '');
        a.textContent = p.title;
        links.appendChild(a);
      }});

      /* More dropdown */
      if (overflow.length > 0) {{
        var overflowActive = overflow.some(function(p) {{ return p.path === currentPath; }});

        var moreWrap = document.createElement('div');
        moreWrap.className = 'sn-more-wrap';

        var moreBtn = document.createElement('button');
        moreBtn.className = 'sn-btn sn-more-btn' + (overflowActive ? ' active' : '');
        moreBtn.setAttribute('aria-haspopup', 'true');
        moreBtn.setAttribute('aria-expanded', 'false');
        moreBtn.innerHTML = 'More <span class="sn-chevron">▼</span>';

        var dropdown = document.createElement('div');
        dropdown.className = 'sn-dropdown';
        dropdown.setAttribute('role', 'menu');

        overflow.forEach(function(p) {{
          var item = document.createElement('a');
          item.href = p.path;
          item.className = 'sn-drop-item' + (currentPath === p.path ? ' active' : '');
          item.setAttribute('role', 'menuitem');
          item.innerHTML = '<span class="sn-drop-bullet">›</span>' + p.title;
          dropdown.appendChild(item);
        }});

        moreBtn.addEventListener('click', function(e) {{
          e.stopPropagation();
          var isOpen = dropdown.classList.toggle('open');
          moreBtn.classList.toggle('open', isOpen);
          moreBtn.querySelector('.sn-chevron').textContent = isOpen ? '▲' : '▼';
          moreBtn.setAttribute('aria-expanded', String(isOpen));
        }});

        document.addEventListener('click', function() {{
          dropdown.classList.remove('open');
          moreBtn.classList.remove('open');
          moreBtn.querySelector('.sn-chevron').textContent = '▼';
          moreBtn.setAttribute('aria-expanded', 'false');
        }});

        moreWrap.appendChild(moreBtn);
        moreWrap.appendChild(dropdown);
        links.appendChild(moreWrap);
      }}

      nav.appendChild(links);
      document.body.prepend(nav);

      /* Push body down to avoid content hidden behind sticky nav */
      document.body.style.paddingTop = 'calc(52px + ' +
        (parseInt(getComputedStyle(document.body).paddingTop) || 0) + 'px)';
    }})
    .catch(function(e) {{ console.error('[site-nav] Failed to load pages.json', e); }});
}})();
</script>
"""

    inject = nav_style + nav_script

    if "</head>" in content:
        # font import を head の早い段階に入れる
        content = content.replace("</head>", nav_style + "</head>", 1)
        # スクリプトは body 末尾
        content = content.replace("</body>", nav_script + "\n</body>", 1)
    elif "</body>" in content:
        content = content.replace("</body>", inject + "\n</body>", 1)
    else:
        content += inject

    html_path.write_text(content, encoding="utf-8")


def _clean_synced_content() -> None:
    """前回同期分をクリア（リポジトリ側のファイルは残す）."""
    manifest = Path(".drive-sync-manifest")

    if COMPILED_DIR.exists():
        shutil.rmtree(COMPILED_DIR)
    COMPILED_DIR.mkdir(parents=True, exist_ok=True)

    if manifest.exists():
        for line in manifest.read_text().splitlines():
            p = Path(line.strip())
            if p.exists() and p.is_file():
                p.unlink()
        for dirpath in sorted(STATIC_DIR.rglob("*"), reverse=True):
            if dirpath.is_dir() and not any(dirpath.iterdir()):
                dirpath.rmdir()

    manifest.unlink(missing_ok=True)


def _record_manifest(synced_files: list[Path]) -> None:
    """同期したファイルのパスをマニフェストに記録."""
    manifest = Path(".drive-sync-manifest")
    manifest.write_text("\n".join(str(p) for p in synced_files) + "\n")


def _extract_html_title(path: Path) -> str:
    """HTML ファイルの <title> タグからタイトルを取得する. 見つからなければファイル名を返す."""
    try:
        # <title> は必ず <head> 内にあるので先頭 4 KB だけ読めば十分
        with path.open(encoding="utf-8", errors="ignore") as f:
            head_chunk = f.read(4096)
        m = re.search(r"<title[^>]*>(.*?)</title>", head_chunk, re.IGNORECASE | re.DOTALL)
        if m:
            title = html.unescape(re.sub(r"\s+", " ", m.group(1)).strip())
            if title:
                return title
    except OSError:
        pass
    return path.stem


def _record_pages_index(synced_files: list[Path]) -> None:
    """フロントエンドのナビゲーション用に index を生成."""
    pages = []

    for p in synced_files:
        if p.suffix == ".html" and "public" in p.parts:
            idx = p.parts.index("public")
            rel_parts = p.parts[idx + 1:]
            rel_path = "/".join(rel_parts)
            title = _extract_html_title(p)
            pages.append({"title": title, "path": f"/{rel_path}"})
        elif p.suffix in COMPILABLE_EXTENSIONS and "src" in p.parts and "content" in p.parts:
            idx = p.parts.index("content")
            rel_parts = p.parts[idx + 1:]
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
