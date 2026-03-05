/**
 * Google Drive 変更検知 → GitHub Actions 発火スクリプト
 *
 * セットアップ:
 *   1. https://script.google.com で新規プロジェクト作成
 *   2. このコードを貼り付け
 *   3. 下記の定数を自分の値に書き換え
 *   4. スクリプトプロパティに GITHUB_TOKEN を設定
 *      - GitHub > Settings > Developer settings > Fine-grained tokens
 *      - Repository access: 対象リポジトリのみ
 *      - Permissions: Actions (Read and Write)
 *   5. checkForChangesAndDeploy にトリガーを設定（時間主導型 > 5分おき）
 */

/** @type {string} GitHub リポジトリ (owner/repo) */
const GITHUB_REPO = "your-username/my-private-site";

/** @type {string} 監視対象の Google Drive フォルダ ID */
const DRIVE_FOLDER_ID = "your-drive-folder-id";

/**
 * メインエントリ: 変更を検知して GitHub Actions を発火する
 * トリガー: 時間主導型（5分おき）
 */
function checkForChangesAndDeploy() {
  const props = PropertiesService.getScriptProperties();
  const lastCheck = props.getProperty("LAST_CHECK");
  const now = new Date();
  const since = lastCheck ? new Date(lastCheck) : now;

  const folder = DriveApp.getFolderById(DRIVE_FOLDER_ID);

  if (hasRecentChanges(folder, since)) {
    triggerGitHubActions();
    Logger.log("変更検知 → GitHub Actions を発火");
  } else {
    Logger.log("変更なし");
  }

  props.setProperty("LAST_CHECK", now.toISOString());
}

/**
 * フォルダ内のファイルが指定時刻以降に更新されたか再帰的に確認
 * @param {GoogleAppsScript.Drive.Folder} folder
 * @param {Date} since
 * @returns {boolean}
 */
function hasRecentChanges(folder, since) {
  var files = folder.getFiles();
  while (files.hasNext()) {
    if (files.next().getLastUpdated() > since) {
      return true;
    }
  }

  var subfolders = folder.getFolders();
  while (subfolders.hasNext()) {
    if (hasRecentChanges(subfolders.next(), since)) {
      return true;
    }
  }

  return false;
}

/**
 * GitHub Actions の repository_dispatch イベントを発火
 */
function triggerGitHubActions() {
  var token = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN");
  if (!token) {
    Logger.log("ERROR: GITHUB_TOKEN が設定されていません");
    return;
  }

  var url = "https://api.github.com/repos/" + GITHUB_REPO + "/dispatches";
  var options = {
    method: "post",
    contentType: "application/json",
    headers: {
      Authorization: "Bearer " + token,
      Accept: "application/vnd.github.v3+json",
    },
    payload: JSON.stringify({
      event_type: "drive-content-updated",
      client_payload: {
        timestamp: new Date().toISOString(),
      },
    }),
    muteHttpExceptions: true,
  };

  var response = UrlFetchApp.fetch(url, options);
  var code = response.getResponseCode();

  if (code === 204) {
    Logger.log("GitHub Actions dispatch 成功");
  } else {
    Logger.log("GitHub Actions dispatch 失敗: " + code + " " + response.getContentText());
  }
}

/**
 * 手動テスト用: 強制的に GitHub Actions を発火
 */
function forceDispatch() {
  triggerGitHubActions();
}
