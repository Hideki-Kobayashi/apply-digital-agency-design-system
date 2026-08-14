---
name: apply-digital-agency-design-system
description: デジタル庁デザインシステムの公式Markdownをローカルへ保存し、その根拠に沿ってWebページとUIコンポーネントを作成、改修、レビューする非公式Skill。利用者がデジタル庁デザインシステムを指定した場合、または対象プロジェクトが同システムをUI基準として採用している場合に使用する。「行政らしい見た目」や一般的なアクセシビリティ依頼だけでは使用しない。
---

# デジタル庁デザインシステムを適用する

以下の`<skill-root>`はこの`SKILL.md`があるディレクトリの絶対パス、`<python>`はPython 3.10以上を実行できるコマンドとする。

## 実行手順

1. Skillを使うたびに、外部通信なしでローカルDADSデータの状態を確認する。

   ```sh
   <python> <skill-root>/scripts/dads.py status
   ```

2. `installed`が`false`なら、公式ZIPの取得と導入を行ってよいか利用者へ確認する。
   同意後、`ax`で[公式リソースページ](https://design.digital.go.jp/dads/resources/)から最新のZIP URLを特定し、次を実行する。

   ```sh
   <python> <skill-root>/scripts/dads.py install \
     --url '<公式ZIP URL>' \
     --network-approved
   ```

   `ax`がない場合または取得に失敗した場合は、公式ページまたはZIP URLからの手動ダウンロードを案内する。
   ZIPの絶対パスを受け取り、`--archive-file`で導入する。

   ```sh
   <python> <skill-root>/scripts/dads.py install \
     --archive-file '<ZIPの絶対パス>'
   ```

3. 手順1の結果が`installed: true`で、次のどちらかに該当する場合は、追加の確認を求めず公式更新確認を実行する。

   - `check_due: true`
   - 利用者が最新版の確認または更新を明示的に依頼した

   ```sh
   <python> <skill-root>/scripts/dads.py check
   ```

   `check`は`ax`で公式リソースページだけを読み、最新のZIP URLと保存済みのURLを比較する。
   ZIPの取得または`current`の置換は行わない。
   成功時は差分の有無にかかわらず確認日時を更新する。

   その起動で実行した`check`が`changed: false`を返したら、利用者へ案内せず通常作業を続ける。
   `changed: true`を返した場合だけ更新の同意を求め、同意後に次を実行する。

   ```sh
   <python> <skill-root>/scripts/dads.py install \
     --url '<公式ZIP URL>' \
     --network-approved \
     --replace
   ```

   `check_due`が`false`なら、`status`の`update_available`が`true`でも再案内しない。

4. `ax`がない場合または公式更新確認に失敗した場合は、確認日時を更新せず、公式リソースページまたはZIP URLからの手動ダウンロードを案内する。
   ZIPの絶対パスを受け取り、まず差分だけを確認する。

   ```sh
   <python> <skill-root>/scripts/dads.py check \
     --archive-file '<ZIPの絶対パス>'
   ```

   `changed: false`なら案内を行わず通常作業を続ける。
   `changed: true`の場合だけ適用の同意を求め、同意後に同じZIPを導入する。

   ```sh
   <python> <skill-root>/scripts/dads.py install \
     --archive-file '<ZIPの絶対パス>' \
     --replace
   ```

5. `status`の`current_dir`を対象に、`rg`で関連するMarkdownを検索する。

   ```sh
   rg -n -i '<検索語>' '<current_dir>' -g '*.md'
   ```

6. 画面全体に影響する`foundations`の関連資料を読んでから、対象UIに対応する`components`の資料を読む。
   必要な場合だけ、その他のガイダンスを読む。

7. 読んだ公式Markdownを根拠に、依頼された作成、改修、レビューを行う。
   既存UIは、現在のスタイルと制約を先に確認する。
   公式資料にないトークン、クラス名、仕様を作らない。
   レビュー依頼ではファイルを変更しない。

## 報告

参照したMarkdown、適用した基本デザイン、未確認事項、意図的な逸脱を簡潔に示す。
画面確認だけを根拠に、デジタル庁デザインシステムまたはWCAGへの完全適合を宣言しない。
