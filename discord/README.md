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
