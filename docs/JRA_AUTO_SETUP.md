# KEIBA LAB: JRA中央競馬の全自動配信を有効化する方法

## 実装状況
KEIBA LAB v3.19はサーバー定期実行・予想作成・15分前固定・結果照合・スマホ表示まで実装済みです。**JRAの実データ取得は未接続**です。通常のJRA-VAN Data Lab.契約ではデータのWeb公開・再配布は禁止されており、公開Webアプリで利用するにはJRADBなど公開用途に適した契約が必要です。予想などの派生情報を公開できるかも契約先と確認してください。

公式案内: https://developer.jra-van.jp/t/topic/899
規約: https://jra-van.jp/info/rule.html

## 契約後の設定
リポジトリの Settings → Secrets and variables → Actions にて以下を設定します。APIキーはコミットやブラウザへ貼らないでください。

- Repository secret **JRA_LICENSED_FEED_URL**: 公開・自動利用の許諾を受けたHTTPS JSONアダプタURL（必須）
- Repository secret **JRA_LICENSED_FEED_TOKEN**: Bearerトークン（認証が必要な場合）
- Repository secret **JRA_LICENSED_RESULTS_URL**: 結果配信先を分ける場合のHTTPS JSON URL（任意）
- Repository variable **JRA_PUBLICATION_RIGHTS_CONFIRMED**: 公開利用・再配信・必要な派生表示を許諾された場合のみ **true** （必須）

URLと公開許諾の変数がそろわなければ**実データへの接続は開始しません**。

GitHub Actions の **JRA licensed-data automatic forecasts** を1回手動実行して正常なデータを確認してください。その後は日本時間06:00〜19:55の間、約5分間隔のスケジュールで実行します。GitHub Actionsの遅延や休止、情報源の欠測は起こり得ます。

## 配信先JSON形式
下記は**架空の開発用サンプル**であり、JRADBがこの形式を直接提供することを意味しません。契約先が返すデータを下記形式へ変換するライセンス適合アダプタが必要です。

~~~json
{
  "races": [{
    "date": "2099-01-01", "venue": "東京", "race_no": 11,
    "name": "架空の開発用11R",
    "start_at": "2099-01-01T15:40:00+09:00",
    "horses": [
      {"no": 1, "name": "架空A", "odds": 3.2},
      {"no": 2, "name": "架空B", "odds": 6.5},
      {"no": 3, "name": "架空C", "odds": 12.0}
    ]
  }],
  "results": [{
    "date": "2099-01-01", "venue": "東京", "race_no": 11,
    "confirmed": true, "result": [1, 2, 3],
    "payouts": {"win": 320, "trio": 1430, "trifecta": 5240}
  }]
}
~~~

結果だけ別配信する場合は同じ構造のresults配列を返してください。着順は正式確定した場合のみ confirmed を true にしてください。払戻金は100円あたり。未取得の値は省略し、架空の金額を補完しません。出馬表には3～18頭すべての馬番・馬名・単勝オッズ・発走時刻が必要です。

## 自動化のルール
1. 出馬表を取得したら、発走15分前より前に限り事前予想を生成・更新。
2. 締切後は最後の事前予想を固定し、**あとから新たな予想を生成しない**。
3. 確定結果の到着後に固定予想と照合し、的中率を算出。
4. 保存は直近21日分。データ取得が止まったときは更新が古いと警告。
5. 自動投票はしません。

モデルは単勝オッズから計算する**市場支持率と着順近似**であり、学習済みAIではありません。利益・的中を保証しません。

## テスト
~~~sh
python scripts/update_jra.py --selftest
node tests/jra-auto.test.cjs
~~~

**未完了の外部条件:** (1) 公開利用できるJRAデータの許諾、(2)配信先とフォーマット変換アダプタ、(3)GitHubの設定。これらがなければ予想データは表示されません。
