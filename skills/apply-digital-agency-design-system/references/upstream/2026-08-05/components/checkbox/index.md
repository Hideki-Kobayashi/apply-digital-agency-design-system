---
title: "チェックボックス 概要"
category: "components"
slug: "checkbox"
document_type: "reference"
source_url: "https://design.digital.go.jp/dads/components/checkbox/"
language: "ja"
---

# チェックボックス （ 概要 ）

[2025年9月10日更新](changelog.md)

![スクリーンショット：未チェックおよびチェック済みのチェックボックスが、それぞれS、M、Lサイズで並んでいる](https://design.digital.go.jp/dads/images/components/checkbox/overview/checkbox_overview.png)

チェックボックスは、複数の項目の中から複数の選択肢を選ぶことを可能にします。また、ひとつの選択肢のオン・オフの切り替えにも用いることができます。

## 仕様

### パーツ

![スクリーンショット：チェックボックスを構成する各パーツに、それぞれ①②の番号を割り付けている。①はチェックボックス。②は選択肢ラベル。チェックボックスの右に配置。](https://design.digital.go.jp/dads/images/components/checkbox/overview/checkbox_anatomy.png)

- ① チェックボックス
- ② 選択肢ラベル

## 使い方

### 設計の原則

- 複数の選択肢からひとつの項目しか選択できない場合は、必ずラジオボタンを使用してください。
- チェックボックスはテキストの左側に配置してください。画面を拡大表示している利用者でも見つけやすくなります。
- ラベルテキストは入力項目を端的に表現してください。入力項目が1つしかなく、その意味を画面タイトルなどで明確に説明できる場合は省略可能です。

#### 良い例

![スクリーンショット：好きな食べ物をすべて選んでください。※必須。3つのチェックボックスの選択肢：りんご、バナナ、みかん](https://design.digital.go.jp/dads/images/components/checkbox/overview/checkbox_example_1.png)

複数の選択肢を選ぶことができる質問に使用しています。

#### 悪い例

![スクリーンショット：あなたは申請者本人ですか？※必須。3つのチェックボックス選択肢：はい、いいえ、回答しない](https://design.digital.go.jp/dads/images/components/checkbox/overview/checkbox_example_2.png)

単一回答を求める質問に使用しています。この場合は、ラジオボタンを使用してください。

## 各種リソース

| 種別       | リソース                                                                                                                                      | 状態  |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------- | --- |
| デザイン     | [Figmaデザインデータ（v2） \[新規タブで開きます\]](https://www.figma.com/community/file/1377880368787735577)                                                | 提供中 |
| HTML版実装  | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-html/tree/main/src/components/checkbox)  | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/html/?path=/docs/components-チェックボックス--docs)                             | 提供中 |
| React版実装 | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-react/tree/main/src/components/Checkbox) | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/react/?path=/docs/component-dads-v2-checkbox--docs)                     | 提供中 |
