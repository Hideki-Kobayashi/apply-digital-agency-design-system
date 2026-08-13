---
title: "ラジオボタン 概要"
category: "components"
slug: "radio"
document_type: "reference"
source_url: "https://design.digital.go.jp/dads/components/radio/"
language: "ja"
---

# ラジオボタン （ 概要 ）

[2025年9月10日更新](changelog.md)

![スクリーンショット：未チェックおよびチェック済みのラジオボタンが、それぞれS、M、Lサイズで並んでいる](https://design.digital.go.jp/dads/images/components/radio/overview/radio_overview.png)

ラジオボタンは、ユーザーが選択肢の中から1つだけを選択できるようにする場合に使用します。

## 仕様

### パーツ

![スクリーンショット：ラジオボタンを構成する各パーツに、それぞれ①②の番号を割り付けている。①はラジオボタン。②は選択肢ラベル。ラジオボタンの右に配置。](https://design.digital.go.jp/dads/images/components/radio/overview/radio_anatomy.png)

- ① ラジオボタン
- ② 選択肢ラベル

## 使い方

### 設計の原則

- 複数の選択肢からひとつの項目だけを選択する場合に使用します。
- ラジオボタンは選択解除ができないので、任意項目で使用する場合は「あてはまるものはない」というような無選択状態を意味する選択肢を設けましょう。

#### 良い例

![スクリーンショット：あなたな上記の条件に当てはまりますか？　※必須。3つのラジオボタンの選択肢：はい、いいえ、どちらとも言えない。「はい」がチェックされている。](https://design.digital.go.jp/dads/images/components/radio/overview/radio_usage_2.png)

ひとつの選択肢を選ぶことができる質問にラジオボタンを使用しています。

#### 悪い例

![スクリーンショット：好きな果物をすべて選んでください。※必須。5つのラジオボタンの選択肢：いちご、もも、梨、みかん、りんご。「いちご」がチェックされている。](https://design.digital.go.jp/dads/images/components/radio/overview/radio_usage_3.png)

複数回答できるような質問にはチェックボックスを使用してください。

## 各種リソース

| 種別       | リソース                                                                                                                                   | 状態  |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------- | --- |
| デザイン     | [Figmaデザインデータ（v2） \[新規タブで開きます\]](https://www.figma.com/community/file/1377880368787735577)                                             | 提供中 |
| HTML版実装  | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-html/tree/main/src/components/radio)  | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/html/?path=/docs/components-ラジオボタン--docs)                            | 提供中 |
| React版実装 | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-react/tree/main/src/components/Radio) | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/react/?path=/docs/component-dads-v2-radio--docs)                     | 提供中 |
