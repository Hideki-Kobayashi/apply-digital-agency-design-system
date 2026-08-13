---
title: "セレクトボックス 概要"
category: "components"
slug: "select"
document_type: "reference"
source_url: "https://design.digital.go.jp/dads/components/select/"
language: "ja"
---

# セレクトボックス （ 概要 ）

[2025年1月9日更新](changelog.md)

![スクリーンショット：ラベル、要否ラベル、サポートテキストで構成されるセレクトボックス](https://design.digital.go.jp/dads/images/components/select/overview/select_overview.png)

## 仕様

### パーツ

![スクリーンショット：セレクトボックスを構成する各パーツに、それぞれ①②③④⑤⑥の番号を割り付けている。①はセレクトボックス。②はセレクトボックスと対になるテキストの項目ラベル。セレクトボックスの上に左寄せで配置。③は赤文字の要否ラベル。項目ラベルの後ろに配置。④はサポートテキスト。ラベルとセレクトボックスの間に配置。⑤は下向きシェブロン（矢印の先端部分のような形状）のドロップダウンアイコン。セレクトボックスの矩形の右端に配置。⑥は赤文字のエラーテキスト。セレクトボックスの下に左寄せで配置。](https://design.digital.go.jp/dads/images/components/select/overview/select_anatomy.png)

- ① セレクトボックス
- ② 項目ラベル
- ③ 要否ラベル
- ④ サポートテキスト
- ⑤ ドロップダウンアイコン
- ⑥ エラーテキスト

※展開時に表示されるリストはOSデフォルトのスタイルを使用してください。

### オプションリストの実装

オプションリストに規定のスタイルはありません。OSの標準のUIを採用してください。

## 使い方

### 設計の原則

- あまりに長いリストは特にモバイルデバイスでの使い勝手を下げてしまうため、事前の質問により選択肢を減らせないか検討してください。
- リストが5つ以下の場合は、ラジオボタンの使用を推奨します。タップやクリックをせずに選択肢の全体が見え、選択がより簡単になります。
- ラベルテキストは入力項目を端的に表現してください。入力項目が1つしかなく、その意味を画面タイトルなどで明確に説明できる場合は省略可能です。

#### 良い例

![スクリーンショット：選択肢が展開されたセレクトボックス。6件の選択肢が表示されている。](https://design.digital.go.jp/dads/images/components/select/overview/select_example_1.png)

選択肢が6個の場合にセレクトボックスを使用しています。

#### 悪い例

![スクリーンショット：選択肢が展開されたセレクトボックス。2件の選択肢が表示されている。](https://design.digital.go.jp/dads/images/components/select/overview/select_example_2.png)

選択肢が2つしかないのに、セレクトボックスを使用しています。選択肢が5個以下の場合は、ラジオボタンを使用してください。

## 各種リソース

| 種別       | リソース                                                                                                                                    | 状態  |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------- | --- |
| デザイン     | [Figmaデザインデータ（v2） \[新規タブで開きます\]](https://www.figma.com/community/file/1377880368787735577)                                              | 提供中 |
| HTML版実装  | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-html/tree/main/src/components/select)  | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/html/?path=/docs/components-セレクトボックス--docs)                           | 提供中 |
| React版実装 | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-react/tree/main/src/components/Select) | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/react/?path=/docs/component-dads-v2-select--docs)                     | 提供中 |
