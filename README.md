# apply-digital-agency-design-system

デジタル庁デザインシステムの公式Markdownを根拠に、WebページとUIコンポーネントの作成、改修、レビューを支援する非公式Agent Skillです。
CodexとClaude Codeで利用できます。

デジタル庁が提供、承認、提携、推奨しているSkillではありません。

## 必要なもの

- Agent Skillsに対応したCodexまたはClaude Code
- Python 3.10以上
- [`ax`](https://github.com/yusukebe/ax)（強く推奨）

`ax`を導入すると、初回の公式Markdown取得と、前回確認から30日以上経過した利用時の更新確認を自動化できます。
`ax`がなくても利用できますが、公式ZIPの手動ダウンロードが必要です。

### ax CLIの導入

macOSまたはLinuxでは、`ax`公式のインストールコマンドを実行します。

```sh
curl -fsSL https://ax.yusuke.run/install | sh
```

導入後、コマンドを実行できることを確認します。

```sh
ax --version
```

Windowsでは、[`ax`のReleases](https://github.com/yusukebe/ax/releases)からWindows用の実行ファイルを取得します。
環境別の詳細は、[`ax`の公式リポジトリ](https://github.com/yusukebe/ax)を確認してください。

### ax Agent Skillの導入

`ax` CLIを導入したら、エージェントへ使い方を伝えるAgent Skillも導入します。

```sh
npx skills add yusukebe/ax
```

画面の案内に従って、利用先のCodexまたはClaude Codeを選択してください。
このコマンドが導入するのはAgent Skillだけです。`ax` CLI本体は別途必要です。

## インストール

### npxを使う

この方法ではNode.js 22.20.0以上が必要です。

```sh
npx skills add https://github.com/Hideki-Kobayashi/apply-digital-agency-design-system/tree/main/skills/apply-digital-agency-design-system -g -a codex -a claude-code
```

この方法は第三者製の[`skills`](https://github.com/vercel-labs/skills) CLIを使います。

### CodexのSkill Installerを使う

Codexへ次のように依頼します。

```text
$skill-installerを使って、https://github.com/Hideki-Kobayashi/apply-digital-agency-design-system/tree/main/skills/apply-digital-agency-design-system からSkillをインストールしてください。
```

### 手動で配置する

このリポジトリの`skills/apply-digital-agency-design-system`を、利用する製品のSkillフォルダへコピーします。

- Codex：`$CODEX_HOME/skills/apply-digital-agency-design-system`（未設定時は`~/.codex/skills/apply-digital-agency-design-system`）
- Claude Code：`~/.claude/skills/apply-digital-agency-design-system`

## 使い方

Skill名を指定するか、デジタル庁デザインシステムを使うことを依頼に含めます。

```text
$apply-digital-agency-design-systemを使って、この申請フォームを改修してください。
```

```text
$apply-digital-agency-design-systemを使って、新しいWebページを作成してください。
```

```text
$apply-digital-agency-design-systemを使って、この画面をレビューしてください。ファイルは変更しないでください。
```

## DADSデータの取得と更新

### 初回利用

初回利用時にローカルDADSデータがなければ、Skillは`ax`で最新の公式ZIPを特定し、同意を求めずに取得して導入します。
取得後は、ローカルに保存したMarkdownを検索して使います。
`ax`がない場合または取得に失敗した場合は、公式ページまたはZIP URLから手動でダウンロードするよう案内します。

### 更新確認

Skillは呼び出されるたびにローカル状態を確認します。
前回の公式確認から30日（720時間）以上経過している場合だけ、事前の同意を求めずに`ax`で[公式リソースページ](https://design.digital.go.jp/dads/resources/)を確認します。
この確認はページを読んでZIP URLを比較するだけで、ZIPを取得しません。

確認に成功したら、差分の有無にかかわらず確認日時を更新します。
差分がなければ、そのまま作業を続けます。
その回の確認で新しいZIP URLが見つかった場合だけ、ZIPの取得と置換を行ってよいか確認します。
更新を見送った場合も、同じ案内は次の公式確認まで繰り返しません。
最新版の確認または更新を明示的に依頼した場合は、30日未満でも確認します。

### 手動ダウンロード

導入済みの状態で`ax`による確認に失敗した場合も、公式ページまたはZIP URLから最新のZIPを手動でダウンロードするよう案内します。
導入済みの場合は先に差分だけを確認します。
差分がある場合だけ適用の同意を求めます。
失敗した確認は、確認済みとして記録しません。

## ライセンスと出典

独自に作成したコードと文書にはMIT Licenseを適用し、デジタル庁由来のコンテンツにはデジタル庁の利用条件を適用します。
詳細は[`LICENSE`](LICENSE)と[`NOTICE.md`](NOTICE.md)を確認してください。

出典：[デジタル庁デザインシステムウェブサイト](https://design.digital.go.jp/dads/)

デジタル庁デザインシステムウェブサイトをもとにHideki-KobayashiがAgent Skill向けに加工して作成。
