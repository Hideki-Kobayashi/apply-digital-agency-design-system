---
title: "テキストエリア 概要"
category: "components"
slug: "textarea"
document_type: "reference"
source_url: "https://design.digital.go.jp/dads/components/textarea/"
language: "ja"
---

# テキストエリア （ 概要 ）

[2025年12月24日更新](changelog.md)

![スクリーンショット：ラベル、要否ラベル、サポートテキスト、文字数カウンターのパーツで構成されるテキストエリア。](https://design.digital.go.jp/dads/images/components/textarea/overview/textarea_overview.png)

## 仕様

### パーツ

![スクリーンショット：テキストエリアを構成する各パーツに、それぞれ①②③④⑤⑥の番号を割り付けている。①はテキストの入力フィールド。②は入力フィールドと対になるテキストの項目ラベル。入力フィールドの上に左寄せで配置。③は赤文字の要否ラベル。項目ラベルの後ろに配置。④はサポートテキスト。ラベルと入力フィールドの間に配置。⑤は文字数カウンター入力フィールドの下に左寄せで配置。⑥は赤文字のエラーテキスト。文字数カウンターの下に左寄せで配置。](https://design.digital.go.jp/dads/images/components/textarea/overview/textarea_anatomy.png)

- ① 入力フィールド（必須）
- ② 項目ラベル（必須）
- ③ 要否ラベル
- ④ サポートテキスト
- ⑤ 文字数カウンター
- ⑥ エラーテキスト

## 使い方

### 設計の原則

- 自由入力形式の回答は、利用者にとって負荷の高いものです。例えば、「その他を選んだ方だけご記入ください」等、質問を分割した後の使用を検討してください。
- ラベルテキストは入力項目を端的に表現してください。入力項目が1つしかなく、その意味を画面タイトルなどで明確に説明できる場合は省略可能です。

#### 良い例

![スクリーンショット：「どの機能に問題がありましたか？」というラベルで3択のラジオボタンを提示する質問項目と、「詳しい状況を教えてください」というラベルで100文字以内のテキスト入力を求める質問項目。](https://design.digital.go.jp/dads/images/components/textarea/overview/textarea_label_1.png)

質問が分解され、最低限の記述で済んでいます。

#### 悪い例

![スクリーンショット：「どこに問題があるか教えてください」というラベルで100文字以内のテキスト入力を求める質問項目。](https://design.digital.go.jp/dads/images/components/textarea/overview/textarea_label_2.png)

質問がオープンすぎると入力に負荷がかかってしまいます。

### 文字数に制限がある場合

入力項目に文字数制限がある場合は、ラベルに最大文字数を具体的に記述しましょう。

最大文字数が、おおむね20文字を超える、もしくは、入力フィールド内でスクロールが必要な文字数以上の場合は、文字数カウンターを合わせて表示することで、入力者が目視で入力した文字数を把握できるようにします。

#### 良い例

![スクリーンショット：「困っていることを100文字以内で教えてください」というラベルのテキストエリアで、テキストエリア下部には、エラーテキストとして「＊入力できる文字数を超えています」の表示と、赤色に変化した文字数カウンターが配置されている。](https://design.digital.go.jp/dads/images/components/textarea/overview/textarea_length_1.png)

ラベルで文字数の制限を明示し、文字数カウンターを常時表示しています。制限を超えた場合は超過文字数を知ることができます。

#### 良い例

![スクリーンショット：「困っていることを100文字以内で教えてください」というラベルのエラー状態のテキストエリアで、エラーテキストは「＊入力できる文字数を超えています。（入力文字数101文字）」](https://design.digital.go.jp/dads/images/components/textarea/overview/textarea_length_2.png)

ラベルで文字数の制限を明示し、文字数制限を超えた場合はエラーを表示しています。入力済みの文字数を表示することで、修正がしやすくなっています。

#### 悪い例

![スクリーンショット：「困っていることを教えてください」というラベルのテキストエリアで、エラーテキストは「＊入力できる文字数は100文字までです。」](https://design.digital.go.jp/dads/images/components/textarea/overview/textarea_length_3.png)

ラベルで文字数の制限を示していません。エラーが出てはじめて何文字まで入力できるのかが分かります。

#### 悪い例

![スクリーンショット：「困っていることを教えてください」というラベルのテキストエリアで、エラーテキストは「＊入力できる文字数を超えています。」](https://design.digital.go.jp/dads/images/components/textarea/overview/textarea_length_4.png)

ラベルで文字数の制限を示していません。エラーが出ても何文字まで許容されるのか分かりません。

## 各種リソース

| 種別       | リソース                                                                                                                                      | 状態  |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------- | --- |
| デザイン     | [Figmaデザインデータ（v2） \[新規タブで開きます\]](https://www.figma.com/community/file/1377880368787735577)                                                | 提供中 |
| HTML版実装  | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-html/tree/main/src/components/textarea)  | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/html/?path=/docs/components-テキストエリア--docs)                              | 提供中 |
| React版実装 | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-react/tree/main/src/components/Textarea) | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/react/?path=/docs/component-dads-v2-textarea--docs)                     | 提供中 |
