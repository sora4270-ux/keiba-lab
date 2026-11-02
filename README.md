# KEIBA LAB v3.2 — iPhone継続利用・公開用パッケージ

このファイル群を **同じフォルダ構造のまま** GitHub Pages等のHTTPSサイトへ配置すると、iPhoneホーム画面から起動できます。`index.html`単体は通常のアプリとして動きますが、オフライン起動等には `sw.js`, `manifest.webmanifest`, `icons/` を含むHTTPS公開が必要です。

## GitHub Pagesで無料公開（GitHub Freeは公開リポジトリが必要）
1. GitHubにサインインし、New repositoryを押す。リポジトリ名を例 `keiba-lab` とし **Public** で作成する。
2. リポジトリの `Add file` → `Upload files` からZIPを解凍した中身の `index.html`, `sw.js`, `manifest.webmanifest`, `.nojekyll`, `icons/` などをアップロードする。ZIP自体だけをアップロードしても動きません。
3. `Commit changes` を押す。
4. `Settings` → `Pages` → `Build and deployment` の `Source`: **Deploy from a branch** → `main` → `/(root)` → `Save` を押す。
5. Pagesに表示された公開URLをSafariで開く。例: `https://GitHubユーザー名.github.io/keiba-lab/`（実際のURLはGitHubで確認）。
6. Safari共有メニュー → `ホーム画面に追加` → `Webアプリとして開く` → `追加`。

## 継続利用上の重要事項
- 予想・的中率・モデル・最近取り込んだレース一覧は**その端末のWebアプリ内**で保存。クラウド自動同期や24時間バックグラウンド実行は実装されていません。
- iPhone Safariとホーム画面のWebアプリはデータ領域が異なることがあります。**追加前に「全データをバックアップ」、追加後に「全データを復元」**してください。
- ホーム画面から起動した状態で、定期的に「全データをバックアップ」を押し、JSONをiCloud Drive等へ保管してください。
- 前回取り込んだレース一覧は保持しますが**最新の出馬表ではありません**。利用前に公式情報で更新してください。
- 初期状態は**デモ用の架空馬**を使います。現実の予想精度・利益を示すものではありません。
- 許諾された外部JSONフィードを設定しない限り、JRA/地方競馬から自動取得しません。データフィードは利用者が用意する必要があります。
- 的中率は確定結果を入力してから表示されます。確定結果のない予想は集計対象外です。
- 公開サイトの`index.html`等は誰でも読める可能性があります。**個人情報・APIキー・契約データをGitHubにアップロードしない**でください。ローカルのJSONバックアップも公開しないでください。
- GitHub Pagesを公開していても、利用者の端末ストレージが消去されると履歴が失われます。予想履歴はGitHub上には保存されません。

## 動作・テスト
起動は`index.html`。ホーム画面への追加とオフライン起動はHTTPS公開時にのみ有効。端末内のstorage削除や別originでの公開はデータ引継ぎになりません。

開発・分析用ツールであり、馬券の購入機能はありません。未学習状態のモデル予想に的中保証はありません。