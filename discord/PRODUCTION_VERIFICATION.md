# 本番検証を通して朝の生成を再開する

## 現時点

2026-10-21、初回の本番検証9項目・実配信・sent照合を完了し、朝の生成タスクを再開した。
GitHubの既存配信cronは変更しない。mainの候補原稿のpushから検証を自動起動し、
真正の成功artifactを確認してからoutboxへ進める。候補の登録だけでは配信しない。

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
- `verification_requirements`: 個別メニュー・月次チェックだけの既存プロファイルは次の配列（順序も固定）
  `["unauthenticated-denied","individual-menu","monthly-read","monthly-write-restore","source-stable"]`

132〜142版を集約する原稿には、上記5項目に次の4項目をこの順で追加した
9項目の拡張プロファイルを使用する。
`["public-referral","cream-lp","video-id-entry","notification-not-ready"]`
既存の5項目成功artifactは、拡張後の原稿とはハッシュが異なるため流用できない。
任意のチェック名・一部省略は拒否する。新たな対象機能は対応する検証を追加するまで告知しない。

## 3. 本番の画面と操作を検証する

mainの1回のpushで `discord/candidates/estlela-vNNN.json` を1件だけ追加・更新する。
`ESTLELA production verification` がイベントの不変コミットをcheckoutし、変更された候補を
安全に選択して実行する。複数候補・無効なパス・削除だけのpushは拒否する。
日々の生成はGitHubコネクタのGit tree/commit/ref操作でこのpushを作る。
Actionsの手動実行でも、mainのcandidateに上記のパスを指定できる。
環境Secretがない場合、または事前確認に失敗する場合はブロックされる。

CloudflareのJavaScript Detectionsが注入される場合、検証の通信制限が通常の確認処理も
遮断することがある。所有者は今回の復旧で通常のJavaScript Detectionsの実行を承認済み。
main候補pushでは通常の確認処理を実行し、手動実行は `allow_cloudflare_jsd` で選ぶ（既定false）。
検証対象のサポート・動画の各オリジンの
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

拡張プロファイルは公開トップ、紹介者IDを保ったLP共有、クリームLPと画像、
公式登録・購入リンクのリダイレクト先（追跡せず）、動画のID選択フォームを確認する。
LPは常にpreview=1で開く。動画フォームはサポートIDの初期選択・別ID・桁数検証を
確認するが送信しない。毎回新しい検証用動画利用者を作って利用件数を増やさないためである。
実際の999999によるID選択後の作成画面・同じブラウザーの履歴・従来の本人確認付き履歴は
2026-10-21に別途実操作で確認した。動画URLの作成・送信・視聴開始はしていない。
スマホ通知は「準備中」の無効ボタンを確認する。配信開始とは扱わず、原稿にも含めない。

ブラウザーは他のID、管理者API、通知登録、動画作成・会員登録のPOST、外部への通信を遮断する。
公開トップの集計POSTと無関係な商品画像1件は送信せず検証対象外とする。
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
初回のsent照合後に当日の記録・復旧経緯・生成タスクの現在の比較基準を更新する。
Issue #1は解消確認まで開いたままにする。

## 送信しないテスト

```bash
python -m unittest discover -s discord -p 'test_*.py'
python discord/publish_updates.py --check-only
```

テストの成功は本番表示やDiscordへの実送信の証明ではない。
テストは一時ディレクトリと模擬Discord応答を使い、PNG生成は実コードを実行する。
既存の配信記録と送信結果不明時の停止も確認する。

