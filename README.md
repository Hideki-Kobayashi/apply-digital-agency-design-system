# apply-digital-agency-design-system

デジタル庁デザインシステムの公式Markdownを根拠に、WebページとUIコンポーネントの作成、改修、レビューを支援する非公式Codex Skillです。

デジタル庁が提供、承認、提携または推奨しているSkillではありません。

## できること

- 新規ページに必要な基本デザインを整理する。
- 既存UIを、維持、移行、意図的な逸脱に分けて改修する。
- 個別コンポーネントに必要な公式資料を選び、実装またはレビューする。
- 公式の選択肢、既定値、例、原則、要件、固定値を区別する。
- デジタル庁が配布するMarkdownの更新を確認する。

通常作業では外部通信を行いません。

## 必要なもの

- Codex
- Python 3.10以上

macOS、Linux、Windowsに対応しています。

公式資料の更新確認では、[`ax`](https://github.com/yusukebe/ax)が見つかれば自動で利用します。`ax`は推奨ですが必須ではありません。

## インストールと更新

Codexへ次のように依頼してください。

```text
$skill-installerを使って、https://github.com/Hideki-Kobayashi/apply-digital-agency-design-system/tree/main/skills/apply-digital-agency-design-system からSkillをインストールしてください。
```

インストール済みのSkill本体を確認または更新する場合は、このSkillへ明示的に依頼します。

```text
$apply-digital-agency-design-systemを使って、Skill本体の最新版を確認してください。
```

```text
$apply-digital-agency-design-systemを使って、Skill本体を最新版へ更新してください。
```

確認だけの依頼ではインストール済みファイルを変更しません。更新時は差分と検証結果を示し、利用者の承認後に置き換えます。

## 使い方

```text
$apply-digital-agency-design-systemを使って、この申請フォームを新規作成してください。
```

```text
$apply-digital-agency-design-systemを使って、既存のボタンと入力欄をデジタル庁デザインシステムに沿って改修してください。
```

```text
$apply-digital-agency-design-systemを使って、この画面をレビューしてください。ファイルは変更しないでください。
```

## 更新確認

### 公式資料

前回の成功確認から30日以上経過すると、依頼された作業を先に完了してから確認を提案します。利用者が同意するまで公式サイトへ接続しません。

変更が見つかった場合は候補として保存し、別の承認があるまで利用中の公式資料を切り替えません。ZIPを自動取得できない場合は、特定済みの公式URLから手動で保存する方法を案内することがあります。

```text
$apply-digital-agency-design-systemを使って、公式資料の最新版を確認してください。
```

### Skill本体

Skill本体は自動確認しません。「Skill本体の最新版を確認して」または「Skill本体を更新して」という明示的な依頼があった場合だけ、GitHubの公開版と比較します。

公式資料の更新確認への同意を、Skill本体の更新許可として扱いません。

## ライセンスと出典

独自に作成したコードと文書にはMIT Licenseを適用し、デジタル庁由来の公式Markdownと派生資料にはデジタル庁の利用条件を適用します。詳細は[`LICENSE`](LICENSE)と[`NOTICE.md`](NOTICE.md)を確認してください。

出典：デジタル庁デザインシステムウェブサイト https://design.digital.go.jp/dads/

デジタル庁デザインシステムウェブサイト https://design.digital.go.jp/dads/ をもとにHideki-KobayashiがCodex Skill向けに加工して作成。

## 問題報告

誤った参照、公式資料との差異、更新確認の不具合は[GitHub Issues](https://github.com/Hideki-Kobayashi/apply-digital-agency-design-system/issues)で報告してください。
