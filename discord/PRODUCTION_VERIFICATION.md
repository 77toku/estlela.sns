# 本番検証を通して朝の生成を再開する

## 現時点

朝のChatGPT生成タスクは停止のまま。GitHubの既存配信cronは変更しない。
本書・テスト・新しい検証経路の追加は、本人用画面の本番確認成功を意味しない。
本番の正規アクセスで一連の検証を完了するまでoutboxを作らない。

個別ページは `ref` だけでは認証されない。署名付き個別URLのトークン、または
そのトークンを検証して発行する `__Host-estlela-mt` Cookieが必要。
管理者の全会員実績APIやDBを使って閲覧URLを探すことはしない。

## 1. 検証専用の正規アクセスを用意する

サイトの `docs/production-verification.md` に従う。

- 所有者が管理する、実利用者と重ならない専用プロフィールを既存の正規機能で作成する。
  名前は `ESTLELA検証専用`。実利用者を改名して代用しない。第三者データを入れない。
- Sites環境変数 `ESTLELA_VERIFICATION_AFFILIATE_ID` に専用IDを設定して再公開する。
- GitHub Environment `estlela-production-verification` を作り、mainのみから実行可能にする。
- その環境のSecret `ESTLELA_VERIFICATION_URL` に専用アカウントの元の個別URLを保存する。
  `https://estlela-business-support.honotoku.chatgpt.site/affiliate-activity?ref=…&token=…`
  の形式。URLは認証情報。チャット・Issue・リポジトリ・ログには貼らない。
- 管理者キー、署名元鍵、Discord Webhookを検証ワークフローへ渡さない。

Secret登録はGitHubの正規設定機能で行う。現在の連携ツールにSecret設定操作がない
場合は所有者が設定する。別の認証経路を作って回避しない。

## 2. 公開済みソースと原稿を対応付ける

Sitesのバージョン・deployment statusと正確なソースを取得し、公開成功を確認する。
対象checkoutで `node scripts/source-fingerprint.mjs` を実行する。
単に「最新保存版」を選ばない。公開版から戻された変更や未検証機能を告知しない。

通常の配信用JSONに次を追加し、`discord/candidates/<release_id>.json` としてmainへ
保存する。candidatesの追加だけではDiscordへ送られない。

- `verification_target.source_commit`: 公開成功した正確な40桁のコミット
- `verification_target.source_fingerprint`: 上記の64桁の計算結果
- `verification_target.deployment_id`: 同じ版の成功したSites deployment ID
- `verification_target.public_version`: 同じ公開版番号、source_versionsの最大値と一致
- `verification_requirements`: 次の配列（順序も固定）
  `["unauthenticated-denied","individual-menu","monthly-read","monthly-write-restore","source-stable"]`

現在の検証対象は個別メニューと月次チェックに限定する。この対象以外の変更が未解決なら
比較基準を進めない。本番137版の動画連携、スマホ通知、別画面の動作がこれで
確認できたとは扱わない。必要なら対象のテストを追加してから原稿化する。

## 3. 本番の画面と操作を検証する

Actionsの `ESTLELA production verification` をmainで手動実行し、candidateに上記のパスを指定。
環境Secretがない場合、または事前確認に失敗する場合はブロックされる。

CloudflareのJavaScript Detectionsが注入される場合、検証の通信制限が通常の確認処理も
遮断することがある。bot対策の確認を実行する承認を得た実行でのみ、手動入力
`allow_cloudflare_jsd` を有効にする（既定はfalse）。同じオリジンの
`/cdn-cgi/challenge-platform/` へのクエリなしGET/POSTだけを通し、本人IDや署名トークンの
アプリ用ヘッダーを渡さない。Cloudflareの判定を通常どおりブラウザーで行い、
対話型の確認やアクセス拒否が出た場合は停止する。
公式説明: https://developers.cloudflare.com/cloudflare-challenges/challenge-types/javascript-detections/

Sitesの編集用ウィジェットは実行せず、正確なスクリプト要求を遮断したまま検証対象外とする。
その他の想定外通信は引き続き失敗。診断は固定の分類と、クエリ・フラグメントを除く
リソース照合用ハッシュのみとし、URL・認証情報・応答本文を保存しない。

検証は専用IDを事前確認してから既存の本人用セッションを作成する。画面のURLに
署名トークンは含めない。実際の390px画面で9枠メニュー・管理ページのリンク・
月次チェックを確認し、専用アカウントのアーカイブチェックを切り替えて再読込し、
元の値に復元する。実行は直列化。期限切れ、月またぎ、復元失敗も失敗扱い。
強制終了等で復元できなかった場合は専用アカウントだけを所有者が確認する。
新規Cookieは通常の90日期限に従う。毎回新規ブラウザーで、Cookieを保存・出力しない。

ブラウザーは他のID、管理者API、通知登録、動画連携、外部への通信を遮断する。
画面画像、トレース、HAR、Cookie、個別実績やエラーの生本文は保存しない。
artifactは可否・ソース識別子・原稿のハッシュだけ。開始・終了の指紋不一致も失敗する。

## 4. 生成から配信へ

成功した実行の `production-verification-<run_id>` artifact内の `verification.json` を取得。
実行URL・対象コミット・正常終了をGitHubで照合したうえで、24時間以内に次を実行する。

```bash
python discord/prepare_update.py --candidate discord/candidates/estlela-vNNN.json --report /path/to/verification.json
python discord/publish_updates.py --check-only
```

実在する版番号に置き換える。架空の成功レポートを作成しない。
これで `discord/verifications/<release_id>.json` と `discord/outbox/<release_id>.json` ができる。
両方を同一コミットでmainへ登録する。既存ファイルは上書きしない。
同じ原稿・公開版・送信結果不明のattemptがあれば停止する。

既存publisherが画像を作り、既存Webhook経由で配信する。送信前にattemptを永続化し、
Discordから返されたmessage IDと原稿ハッシュをsentへ保存する手順は維持する。
新規未送信データにだけ証拠ゲートを適用し、配信済みのoutbox/sent/attemptsを改変しない。
24時間を超えた未送信分は自動配信しない。元の原稿のまま再検証し、根拠を照合してから
既存の検証レポートだけを現行SHA指定で更新する。attemptがあれば先に成否を照合する。

真正のsentとActionsを照合後のみ当日のchecksへdeliveredを記録する。検証前の日時や
過去日の成功は埋めない。生成タスクのプロンプトにもこの手順を反映し、初回の本番検証・
配信・控え照合が完了してから既存07:00タスクを有効化する。
Issue #1は解消確認まで開いたままにする。

## 送信しないテスト

```bash
python -m unittest discover -s discord -p 'test_*.py'
python discord/publish_updates.py --check-only
```

テストの成功は本番表示やDiscordへの実送信の証明ではない。
テストは一時ディレクトリと模擬Discord応答を使い、PNG生成は実コードを実行する。
既存の配信記録と送信結果不明時の停止も確認する。
