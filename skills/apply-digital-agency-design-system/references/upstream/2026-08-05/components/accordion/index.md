---
title: "アコーディオン"
category: "components"
slug: "accordion"
document_type: "reference"
source_url: "https://design.digital.go.jp/dads/components/accordion/"
language: "ja"
---

# アコーディオン （ 概要 ）

[2026年7月22日更新](changelog.md)

![スクリーンショット：複数のアコーディオンコンポーネントが並んでいて、先頭が開いている。](https://design.digital.go.jp/dads/images/components/accordion/overview/accordion_overview.png)

アコーディオンは、同種のセクションが連続するとき、それらを折りたたんで一覧性を向上する目的で使用します。

## ユースケース

- 同種のセクションが連続する際、それらを一覧として並べつつ、各コンテンツを折りたたみたいとき

  - 「よくある質問」の質問文を一覧として並べつつ、それぞれの質問に対する回答を折りたたんで提示する
  - 「更新履歴」の日付および概要を一覧として並べつつ、それぞれの更新日に対する詳しい内容を折りたたんで提示する
  - 申請者の属性ごとに入力内容が異なる申請手続きで、属性ごとの個別説明を折りたたんで一覧として提示する

## 注意が必要なケース

- 表示領域をコンパクトにするためだけにアコーディオンを使ってはいけません

  ヘッダーの内容で概要が示されているなど、ボディの内容が追加や補足の情報になるといった合理的な理由がある場合だけ、アコーディオンを使うことができます。

- 内容が重要なときにアコーディオンを使っていけません

  折りたたまれているほうに重要な情報が含まれるような使い方をしないでください。原則として、重要な情報は最初から隠さずに表示するようにします。

- 独立した単一のセクションのみをアコーディオンにしてはいけません

  アコーディオンは同種のセクションが連続するときに使用するコンポーネントです。単一セクションのみが想定される箇所での使用は避けてください。ただし、通常複数セクションが想定されるページ構造であるものの、コンテンツ運用の途上において1セクションだけが表出する期間があるというような使用については許容されます。

- セクション内の一部を追加や補足の情報として折りたたむ時はディスクロージャーを使用してください

  アコーディオンはセクション全体を折りたたみ可能にするコンポーネントです。ヘッダー単体で必要な情報が提供されて、それへの追加や補足の情報をボディに折りたたんで格納するものであり、セクション内の一部を折りたたむものではありません。

## 関連コンポーネント

- [ディスクロージャー](../disclosure/index.md)

## 各種リソース

| 種別       | リソース                                                                                                                                       | 状態  |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ | --- |
| デザイン     | [Figmaデザインデータ（v2） \[新規タブで開きます\]](https://www.figma.com/community/file/1377880368787735577)                                                 | 提供中 |
| HTML版実装  | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-html/tree/main/src/components/accordion)  | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/html/?path=/docs/components-アコーディオン--docs)                               | 提供中 |
| React版実装 | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-react/tree/main/src/components/Accordion) | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/react/?path=/docs/component-dads-v2-accordion--docs)                     | 提供中 |

# アコーディオン （ 使い方 ）

[2026年7月22日更新](changelog.md)

## コンポーネント要素

![スクリーンショット：アコーディオンを構成する各パーツに、それぞれ①②③④の番号を割り付けている。①は開閉アイコン。ヘッダーの左に配置。②はヘッダー。③はボディ。ヘッダーの下に配置。④はリターンリンク。](https://design.digital.go.jp/dads/images/components/accordion/usage/accordion_anatomy.png)

- ① 開閉アイコン（必須）
- ② ヘッダー（必須）
- ③ ボディ（必須）
- ④ リターンリンク

### サイズバリエーション

![スクリーンショット：開閉アイコンのサイズパターン。L・M・S・XSの4サイズ。](https://design.digital.go.jp/dads/images/components/accordion/usage/accordion_icon_sizes.png)

開閉アイコンのサイズはL・M・S・XSの4サイズがあります。画面サイズや、コンテンツの性質およびボリュームに基づいて使い分けてください。

### リターンリンクの使い方

ヘッダーに戻って閉じる操作を必要とするときは、リターンリンクを使用できます。

## 配置

### 良い例

![OK例:アコーディオン内ディスクロージャー](https://design.digital.go.jp/dads/images/components/accordion/usage/accordion_placement_1.png)

アコーディオン内にディスクロージャーを配置できます。

アコーディオンとディスクロージャーの組み合わせを行う際は、上記の例に則って使用してください。

### 悪い例

![NG例:リスト内アコーディオン](https://design.digital.go.jp/dads/images/components/accordion/usage/accordion_placement_2.png)

リスト内にアコーディオンを配置することはできません。

![NG例:テーブル内アコーディオン](https://design.digital.go.jp/dads/images/components/accordion/usage/accordion_placement_3.png)

テーブル内にアコーディオンを配置することはできません。

![NG例:アコーディオン内アコーディオン](https://design.digital.go.jp/dads/images/components/accordion/usage/accordion_placement_4.png)

アコーディオン内にアコーディオンを配置することはできません。

![NG例:ディスクロージャー内アコーディオン](https://design.digital.go.jp/dads/images/components/accordion/usage/accordion_placement_5.png)

ディスクロージャー内にアコーディオンを配置することはできません。

アコーディオンは、それ自身がメイン情報であり、見出し・段落・リスト・テーブルなどのコンテンツと同レベルのセクションとして扱うコンポーネントです。そのため、上記のNG例にあたるような配置はできません。

## コンテンツ

### ヘッダーは概要文にする

よくある質問であれば「会員登録の手順は？」、更新履歴であれば「2025年11月5日 軽微な問題を修正しました」など、コンテンツを要約した概要文を記載します。

### ボディ内にはさまざまなコンポーネントを配置できる

![OK例:アコーディオン内ボディに見出し・段落・リスト・テーブルなどのコンテンツを配置した例](https://design.digital.go.jp/dads/images/components/accordion/usage/accordion_contents.png)

アコーディオンのボディには、情報を構成するために必要な様々なコンポーネントを配置することができます。

### リターンリンクのラベルはヘッダーと揃える

リターンリンクのラベルは、たとえば「『会員登録の手順は？』の先頭に戻る」のような、ヘッダーに「の先頭に戻る」を加えるような形とし、ヘッダーと揃えてください。

## ふるまい

### ページ読み込み時に開いておくか閉じておくかを設定する

ページが読み込まれた際に、アコーディオンを開いた状態で表示するか、閉じた状態で表示するかを定めます。

例えば、先頭のアコーディオンコンポーネントを開いて表示しておくと、後続も同じように情報が折りたたまれていることを示唆できます。

### リターンリンクはヘッダーへのページ内リンクとする

リターンリンクのリンク先はヘッダーへのページ内リンクとします。この挙動により、ボディを閉じるための補助として機能するようになります。

## 実装

### details要素を使って実装する

アコーディオンを実装する際は、`<details>`要素を使用します。HTMLの`<details>`要素を使うと、アクセシブルなアコーディオンを容易に実現できます。`<details>`要素を使う場合、後述のキーボード操作とWAI-ARIAの実装は不要になります。

```xml
<details>
  <summary>ヘッダー</summary>
  <div>ボディ</div>
</details>
```

### カスタムコンポーネントとして実装する場合

既存システムの制約等の理由でやむを得ず`<details>`要素を使用せずカスタムコンポーネントとして実装する場合は、キーボードだけを使ってアコーディオンを開閉操作できるようにしてください。また、WAI-ARIAのステートおよびプロパティを適切に付与し、支援技術からもUIの状態にアクセスできるようにしてください。

アコーディオンコンポーネントに求められるキーボード操作要件、WAI-ARIAステートおよびプロパティについては、ARIA Authoring Practices Guide（APG）を参照してください。

#### 参考情報

- [Accordion Pattern (Sections With Show/Hide Functionality) | APG | WAI | W3C](https://www.w3.org/WAI/ARIA/apg/patterns/accordion/)
