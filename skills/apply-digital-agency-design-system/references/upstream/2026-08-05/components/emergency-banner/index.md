---
title: "緊急時バナー 概要"
category: "components"
slug: "emergency-banner"
document_type: "reference"
source_url: "https://design.digital.go.jp/dads/components/emergency-banner/"
language: "ja"
---

# 緊急時バナー （ 概要 ）

[2025年1月21日更新](changelog.md)

![スクリーンショット：緊急時バナーのデスクトップ表示とモバイル表示のパターン。](https://design.digital.go.jp/dads/images/components/emergency-banner/overview/emergency_banner_overview.png)

緊急時バナーは、当該ウェブサイトで本来成すべきコミュニケーションを中断してでもファーストビューを占有して注意を促すためのコンポーネントです。たとえばユーザーの生命や財産に影響をもたらすような事象が発生して直ちに知らせなければならないような緊急性の高い告知のために使用します。緊急時バナーはより迅速にメッセージを伝達するためのコンポーネントであり、最もシンプルな構造での実装ですべてのユーザーが確実に認知できることを最優先したスタイルとなっています。

※長期間にわたり掲載する必要のあるメッセージの場合は、[ノティフィケーションバナー](../notification-banner/index.md)を使用します。

## 仕様

- 緊急時バナーはセマンティックカラーのエラー(Error)を使用します。
- 緊急時バナーはユーザーによって非表示にすることはできません。
- 情報の重要性と独自性から、ユーザーの視線が意図せずとも注視してしまうような、サイト/サービスのトーン＆マナーとは少し異なる違和感のあるスタイルを設定します。

![スクリーンショット：緊急時バナーを構成する各パーツにそれぞれ①②③④の番号を割り付けている。①は太字のバナータイトル。緊急時バナーの領域内、最上部に左寄せで配置。②は年月日などのテキスト。ここでは年月日と記載され、バナータイトルの下に左寄せで配置。③は緊急時バナーの本文となるバナーデスクリプション。年月日などのテキストの下に左寄せで配置。④は赤いアクションボタン。バナーデスクリプションの下に中央寄せで配置。緊急時バナー全体は朱色がかったボーダーで囲まれている。](https://design.digital.go.jp/dads/images/components/emergency-banner/overview/emergency_banner_anatomy.png)

- ① バナータイトル（必須）

  内容の重要性が分かるようなタイトルとします。先頭に「【緊急】」の文字列を配置することで誘目性を高めています。文字数は、タイトルがモバイルでも2行に収まり認知しやすいであろう全角30文字以内程度までとします。

- ② 年月日など

  掲載日以外にも更新日時などの情報を合わせて記載できます。

- ③ バナーデスクリプション（必須）

  概ね全角100文字程度以内までとし、それ以上の長さになる時は緊急情報コンテンツを掲載したページを作成し、そこへリンクします。（※タイトルとあわせてSNSへ全文配信できる程度を文字数の目安としています）

- ④ アクションボタン（リンクがある場合は必須）

  アクションボタンの最小幅は利用可能な表示幅の50%です。モバイル表示の場合は100%です。

### バナーのクリッカブルエリア

![スクリーンショット：緊急時バナーのクリッカブルエリアを表した図。アクションボタンがクリッカブルエリアを示すピンク色の矩形で覆われている。](https://design.digital.go.jp/dads/images/components/emergency-banner/overview/emergency_banner_clickable_area.png)

リンク先がある場合は、アクションボタンをセンタリングで配置します。アクションボタン部分のみがクリッカブルエリアとなります。緊急時バナーはリンク先を1つまで持つことができます。

## 使い方

### 緊急時バナーの配置

緊急時バナーはユーザーへの迅速かつ確実な通知が第一の目的です。すべてのユーザーが最初に、確実に認知できる場所に配置します。

#### ページ上部への配置

緊急時バナーはファーストビューですべてのユーザーに素早く認知できるようにページ上部へ配置します。ヘッダーエリアよりもさらに上に配置しても良いでしょう。

![スクリーンショット：ページの最上部に配置された緊急時バナー。モバイルブラウザでの表示イメージとデスクトップブラウザでの表示イメージ。](https://design.digital.go.jp/dads/images/components/emergency-banner/overview/emergency_banner_placement.png)

- ノティフィケーションバナーなど、他の通知コンテンツが上部に存在する場合はそれらよりも上に配置します。また、他の通知コンテンツとのスペースを十分に取り、緊急時バナーが極めて重要な情報を提示していることを明白なものとします。
- 緊急時バナーは複数設置することができますが、緊急事態のみに限ります。

### 緊急時バナーのタイトル

緊急時バナーのタイトルは具体的に警告内容が伝わる文章を使用します。

- 本文を読む前に、一目で警告内容の概要が伝わるように心がけてください。
- タイトル文字列を「【緊急】」の文字列から開始することで、誘目性を高めてください。

#### 良い例

![スクリーンショット：バナータイトルが「○○地区に避難準備情報が発令されました」である緊急時バナーの例。](https://design.digital.go.jp/dads/images/components/emergency-banner/overview/emergency_banner_appropriated_label_example.png)

バナータイトルに警告の概要が具体的に記述されており、一目で読むべき内容であることを判断できます。

#### 悪い例

![スクリーンショット：バナータイトルが「緊急のお知らせ」である緊急時バナーの例。](https://design.digital.go.jp/dads/images/components/emergency-banner/overview/emergency_banner_inappropriated_label_example.png)

このコンポーネントを使用している時点で「緊急のお知らせ」を示しています。バナータイトルには緊急性をもって知らせるべき具体的な警告の概要を記述しなければなりません。

### 緊急時バナーを長期間に渡って掲示しない

#### 悪い例

![スクリーンショット：長期間に渡り掲示されている緊急時バナーの例。年月日に「2020年2月29日掲載」とあるが、バナーデスクリプションが「(2023年10月1日現在)」という表記から始まっている。](https://design.digital.go.jp/dads/images/components/emergency-banner/overview/emergency_banner_long_posting_example.png)

緊急性をともなって掲示された情報でも、掲載され続けることでアラートによる疲弊（アラート疲れ）が発生して注意喚起の効果が薄れたり無視されたりするようになります。また、ファーストビューを占有し続けるため、本来成すべきコミュニケーションが寸断された状態が維持されてしまいます。長期間にわたり掲載する必要がある場合はノティフィケーションバナーを使用してください。

### 緊急性の高い情報以外に使わない

#### 悪い例

![スクリーンショット：バナータイトルが「年末年始の営業時間について」である緊急時バナーの例。](https://design.digital.go.jp/dads/images/components/emergency-banner/overview/emergency_banner_inappropriated_example.png)

緊急時バナーはユーザーの生命や財産に影響をもたらすような緊急性の高い重要情報の通知に使用します。そうでない場合の通知にはノティフィケーションバナーを使用してください。

### 長すぎるバナーデスクリプションを避ける

#### 悪い例

![スクリーンショット：非常に長い（300文字以上）のテキストがバナーデスクリプションに設定されている緊急時バナーの例。](https://design.digital.go.jp/dads/images/components/emergency-banner/overview/emergency_banner_excessive_content_example.png)

緊急時バナーのデスクリプションは概ね全角100文字以内程度を上限の目安としてください。フラットな文字ベースで詳細情報を的確に伝達することは困難です。緊急性と内容の把握が可能な簡潔なタイトルとデスクリプションとする必要があります。

#### 良い例

![スクリーンショット：緊急時バナーの例「○○地区に避難準備情報が発令されました／2023年1月1日午後0時30分時点／1時23分に○○地区に対して避難準備情報が発令されました。お年寄りの方等避難に時間がかかる方は、直ちに指定避難所へ避難してください。／避難所の地図を確認」](https://design.digital.go.jp/dads/images/components/emergency-banner/overview/emergency_banner_appropriated_example.png)

緊急性と内容の把握が可能な簡潔なタイトルとデスクリプションを提供しており、詳細かつ長文や画像等での説明が必要な案内については詳細ページが用意されている。

### バナーデスクリプションの構成

緊急時バナーはユーザーへ簡潔明瞭で確実に情報が伝達できることを考慮してください。

- 情報内容が端的に認知できるよう、バナーデスクリプションを構成してください。

#### バナーデスクリプションの構成

![スクリーンショット：バナーデスクリプションの内容が、見出しと箇条書きで構造化マークアップされている緊急時バナーの例。](https://design.digital.go.jp/dads/images/components/emergency-banner/overview/emergency_banner_clarified_message_example.png)

簡潔明瞭に情報を伝達するためにバナーデスクリプションを構成してください。

## 各種リソース

| 種別       | リソース                                                                                                                                             | 状態  |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | --- |
| デザイン     | [Figmaデザインデータ（v2） \[新規タブで開きます\]](https://www.figma.com/community/file/1377880368787735577)                                                       | 提供中 |
| HTML版実装  | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-html/tree/main/src/components/emergency-banner) | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/html/?path=/docs/components-緊急時バナー--docs)                                      | 提供中 |
| React版実装 | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-react/tree/main/src/components/EmergencyBanner) | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/react/?path=/docs/component-dads-v2-emergencybanner--docs)                     | 提供中 |
