# apply-digital-agency-design-system

デジタル庁デザインシステムの公式Markdownを根拠に、WebページとUIコンポーネントの作成、改修、レビューを支援する非公式Codex Skillです。

デジタル庁が提供、承認、提携または推奨しているSkillではありません。

## できること

- 新規ページの基本デザインを、カラー、タイポグラフィ、レイアウト、余白などの8分類から決める。
- 既存UIの値を、維持、移行、意図的な逸脱に分けて改修する。
- 個別コンポーネントに必要な公式資料だけを選び、実装またはレビューする。
- 公式の選択肢、既定値、例、原則、要件、固定値を区別する。
- 承認済みの公式Markdownスナップショットを検索し、根拠のURLと参照版を報告する。
- 前回の成功確認から30日以上経過したとき、通常作業の完了後に公式更新の確認を提案する。

通常作業では外部通信を行いません。

更新確認への同意と、見つかった更新候補を有効化する承認も分けています。

## 収録版

| 項目 | 値 |
|---|---|
| スナップショットID | `2026-08-05` |
| デジタル庁デザインシステム版 | `v2.17.0` |
| Markdown公開日 | 2026年8月5日 |
| 公式文書 | 123件 |
| Markdown総数 | 125件 |
| 公式ZIPのSHA-256 | `cde548789a744f53d87997cbefec1ec7feacf8fb3b023bfe9ea07a713de2c8d8` |

版とハッシュの正本は[`source-manifest.json`](skills/apply-digital-agency-design-system/references/source-manifest.json)です。

## 必要なもの

- ChatGPTデスクトップアプリのCodex、Codex CLI、またはCodex IDE拡張。
- Python 3.10以上。

Python部分はmacOS、Linux、Windowsに対応しています。

公式更新の確認にも、追加のCLIは必要ありません。

## 任意の推奨ツール

公式更新の確認では、[`ax`](https://github.com/yusukebe/ax)が見つかる場合、公式ページの取得、最新ZIPのリンク抽出、ZIPの保存を自動で任せます。

`ax`はHTMLから必要なリンクを簡潔かつ明示的に抽出できるため、このリポジトリでは推奨しています。

ただし、インストールは必須ではありません。

`ax`が見つからない場合は、Python標準ライブラリが更新確認全体を代行します。

`ax`経路では、`ax`がHTTPリダイレクトを自動追従します。
リダイレクト後の最終URLは公式ホストか検証しますが、途中の転送先は通信前に検証できません。
転送先も通信前に制限したい場合は、`--fetch-backend stdlib`を使います。

## インストール

Codexで`$skill-installer`を使い、次のURLからインストールする方法を推奨します。

```text
$skill-installerを使って、https://github.com/Hideki-Kobayashi/apply-digital-agency-design-system/tree/main/skills/apply-digital-agency-design-system からSkillをインストールしてください。
```

同名のSkillがすでにある場合、Skill Installerは既存フォルダを上書きしません。

既存版を残すか削除するかを決めてから、もう一度インストールしてください。

手動で導入する場合は、このリポジトリの`skills/apply-digital-agency-design-system`ディレクトリを、Codexが読み込むユーザー用Skillディレクトリへコピーします。

[Codexの現行ドキュメント](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)で案内されているユーザー用ディレクトリは`$HOME/.agents/skills`です。

## 使い方

新規ページの例です。

```text
$apply-digital-agency-design-systemを使って、この申請フォームを新規作成してください。
```

既存UIの改修例です。

```text
$apply-digital-agency-design-systemを使って、既存のボタンと入力欄をデジタル庁デザインシステムに沿って改修してください。
```

レビュー例です。

```text
$apply-digital-agency-design-systemを使って、この画面をレビューしてください。ファイルは変更しないでください。
```

明示的に最新版を確認する例です。

```text
$apply-digital-agency-design-systemを使って、デジタル庁デザインシステムの最新版を確認してください。
```

## 更新確認の動作

Skillは起動時に利用者別のローカル状態だけを読みます。

前回の成功確認から30日以上経過していても、依頼された作業を先に完了し、最後に更新確認を提案するだけです。

利用者が同意するまで公式サイトへ接続しません。

変更が見つかった場合は候補として保存し、候補IDを指定した別の承認があるまで有効版を切り替えません。

取得バックエンドは既定で`auto`です。

- `ax`が見つかる場合は、外部通信とHTML解析を`ax`へ任せる。
- 見つからない場合は、Python標準ライブラリで外部通信とHTML解析を行う。
- 更新確認の開始時に一つを選び、処理の途中で別のバックエンドへ切り替えない。

取得後のURL・容量・ZIP形式の確認、ハッシュ計算、差分作成、状態保存は、どちらの場合もPythonで行います。

動作確認などで取得バックエンドを固定する場合は、更新確認コマンドへ`--fetch-backend ax`または`--fetch-backend stdlib`を指定できます。

実行状態と候補の既定保存先は次のとおりです。

| OS | 保存先 |
|---|---|
| macOS | `~/Library/Application Support/apply-digital-agency-design-system/` |
| Linux | `${XDG_STATE_HOME:-~/.local/state}/apply-digital-agency-design-system/` |
| Windows | `%LOCALAPPDATA%\apply-digital-agency-design-system\` |

環境変数`DADS_SKILL_STATE_DIR`を設定すると、保存先を変更できます。

## リポジトリ構成

```text
skills/apply-digital-agency-design-system/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── foundation-map.md
│   ├── source-manifest.json
│   ├── task-index.md
│   ├── update-contract.json
│   └── upstream/2026-08-05/
└── scripts/
    ├── build_index.py
    ├── manage_upstream.py
    ├── search_guidance.py
    ├── upstream_fetch.py
    ├── verify_snapshot.py
    └── tests/
```

## テスト

リポジトリルートで次を実行します。

```sh
python3 -m unittest discover \
  -s skills/apply-digital-agency-design-system/scripts/tests \
  -v
```

テストには、30日判定、同意前の外部通信禁止、取得バックエンドの自動選択、URL・TLS・容量とZIPの安全確認、更新候補と昇格の分離、公式スナップショットのハッシュ検証、参照索引の整合性が含まれます。

GitHub ActionsではmacOS、Linux、Windowsで同じテストを実行します。

## ライセンスと出典

このリポジトリには、適用条件の異なるファイルが含まれます。

独自に作成したコードと文書にはMIT Licenseを適用し、デジタル庁由来の公式Markdownと派生資料にはデジタル庁の利用条件を適用します。

適用範囲は[`LICENSE`](LICENSE)と[`NOTICE.md`](NOTICE.md)を確認してください。

出典：デジタル庁デザインシステムウェブサイト https://design.digital.go.jp/dads/

デジタル庁デザインシステムウェブサイト https://design.digital.go.jp/dads/ をもとにHideki-KobayashiがCodex Skill向けに加工して作成。

## 問題報告と更新

誤った参照、公式資料との差異、更新確認の不具合はGitHub Issuesで報告してください。

公式資料の更新は、候補の差分と検証結果を確認してからPull Requestとして反映します。
