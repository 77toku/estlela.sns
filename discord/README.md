# ESTLELA Discord 自動投稿

サポートサイトの公開更新を、ブランドデザインの画像と投稿文にしてDiscordへ送信します。

## 初回設定

1. Discordの既存サーバーで、投稿先チャンネルのWebhookを作成します。
2. GitHubリポジトリ 77toku/estlela.sns の Settings を開きます。
3. Secrets and variables、Actions、New repository secret の順に開きます。
4. 名前を DISCORD_WEBHOOK_URL にして、DiscordでコピーしたWebhook URLを登録します。
5. Actions の ESTLELA Discord publisher から Run workflow を一度実行します。

Webhook URLは投稿権限そのものです。ファイル、画面、ログ、チャットには保存しません。

## 処理の流れ

- ChatGPTの毎朝タスクが、未告知の公開変更を discord/outbox にJSONで追加します。
- GitHub Actionsが固定テンプレートから1080×1080のPNGを生成します。
- 投稿文、画像、サイトURLをDiscord Webhookへ送ります。
- Discordから返されたメッセージIDを discord/sent に保存します。
- 同じrelease_idは再送しません。

変更がない日はoutboxファイルを作らないため、Discordにも投稿しません。

## 手動テスト

以下のコマンドで、Discordへ送らず画像だけを確認できます。

python discord/publish_updates.py --render-only discord/example-payload.json --output /tmp/estlela-update.png

実際の送信テストでは、example-payload.jsonを日付と重複しないrelease_idに変更してdiscord/outboxへコピーし、ワークフローを手動実行します。

## 2026-09-24 点検結果と運用

- 生成元はChatGPTタスク「エステレラ更新をDiscordへ自動投稿」。Asia/Tokyo 07:00、日次、有効。点検時の最終起動は2026-09-24 07:03 JST。
- 最新outboxはestlela-v79。2026-09-21 07:07:47 JSTにメッセージID付き配信控えを保存済み。全8件（接続テスト2件を含む）が配信済み。直近publisherの実行は成功。
- Sitesの最新保存バージョンも79。新しいoutboxがないことと整合する。過去の朝タスクの詳細実行結果は取得できていないため、各日の確認成功までは証明できない。
- sidejob-check.ymlは副業診断のCIであり、outbox生成とは無関係。

### スケジュールと観測

ChatGPTの07:00タスクが公開確認・原稿作成を担当する。Actionsのcronは原稿を生成しない。
`0 22 * * *`（UTC、JST翌07:00）で未配信を回収し、`45 22 * * *`（JST07:45）で再確認する。
新しいoutboxのpushでも送信する。GitHubのcronは遅延・欠落があり得るため、7時ちょうどの着信は保証しない。
https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

朝タスクは更新なしの日も `discord/checks/YYYY-MM-DD.json` を記録する。以下のキーを使う（例をそのまま実績として登録しない）：

- `checked_at`: 実際の確認時刻、タイムゾーン付きISO8601
- `cutoff_jst`: 対象日の07:00:00+09:00
- `status`: `no_update` / `queued` / `delivered` / `error`
- `release_ids`: 対象release_id配列。no_updateなら空配列
- `evidence`: 確認済み公開バージョン、公開確認方法、比較基準など。失敗時は秘密情報を含まない失敗理由

07:45以降は当日、それより前は前日の記録を検査する。未記録・error・配信控え欠落はジョブを失敗させる。
失敗時はGitHub Issue `[ESTLELA] Daily update needs attention` を1件作成し、未解決なら本文を更新する。
メール・プッシュの到着はGitHubの個人通知設定に依存する。Issueは確認後に手動で閉じる。
Actions自身が全く起動しない場合にはこのIssue処理も起動しない。朝タスクでも前日のActions実行と記録を照合し、異常をタスク結果で知らせる。

### 重複防止と復旧

- 同じconcurrency groupで直列化し、待機後に最新mainをcheckoutする。
- バッチ全体を送信前検証。同じrelease_idの内容変更、source_versions重複、日付・IDを変えただけの本文重複、控え不整合を拒否する。outbox/sentは履歴として保持する。
- 送信前に `discord/attempts/<release_id>.json` をmainへ永続化できた場合だけ送信する。
- 成功時はDiscordメッセージID付き控えを1件ずつmainへ保存する。
- タイムアウト・5xxなど送信成否不明のPOSTは自動再送しない。429のみ待機再試行する。
- attemptがありsentがない場合は停止する。Discord実物とActionsのdelivery-evidence artifactを確認し、送信済みなら実在メッセージIDを持つ真正の控えを復旧する。未送信と確定した場合だけ該当attemptを削除して手動再実行する。確認前に別IDで再登録しない。
- 送信後の控え保存障害でもartifactにローカル記録を30日保存する。強制終了・ランナー消失時にはartifactが残らない場合がある。
- Secret未設定は成功扱いにしない。

### 送信しない検証

```
python -m unittest discover -s discord -p 'test_*.py'
python discord/publish_updates.py --check-only
python discord/check_health.py
```

本番送信は既存mainのActionsから行う。手元での送信には永続化可能なmain checkoutと `ESTLELA_DURABLE_DELIVERY=1` が必要。
