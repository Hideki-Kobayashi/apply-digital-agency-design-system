---
title: "メニューリスト 概要"
category: "components"
slug: "menu-list"
document_type: "reference"
source_url: "https://design.digital.go.jp/dads/components/menu-list/"
language: "ja"
---

# メニューリスト （ 概要 ）

[2025年1月9日更新](changelog.md)

![スクリーンショット：メニューリストの3つのパターン。](https://design.digital.go.jp/dads/images/components/menu-list/overview/menu_list_overview.png)

メニューアイテムを束ねたコンポーネントです。ローカルメニューとしてコンテンツエリアに配置したり、メニューリストボックスやメガメニューの中などに内包したりして使用します。

## 使い方

### リンクの強調

![スクリーンショット：エンドアイコンの有無の異なる2つのメニューリストが左右に並んでいる。右のメニューリストの各項目には、右向きのシェブロン（矢印の先端部分のような形状）がエンドアイコンとして配置されている。](https://design.digital.go.jp/dads/images/components/menu-list/overview/menu_list_link.png)

- 通常メニュー内のアイテムはそのほとんどがリンクやインタラクションのためのアイテムになりますが、リンクを強調し、視覚的に明確にしたい場合はエンドアイコンを使用します。

- 通常のリンクを強調して示すエンドアイコンと、機能的に異なった第二階層リンク（スライド型）やアコーディオンを示すアイコンと混在させることは、視覚的、体験的に複雑さや認知負荷を与えるため、できる限り使用しないでください。

### CTA（Call‐to‐action）の挙動表示を明確に

- メニュー内のリンク（ページ遷移）とアコーディオン（サブメニューの開閉）など、ユーザーに異なった挙動を想定させる場合は、その表示を明確に違うものにする必要があります。

- エンドアイコンをともなう強調リンクとサブメニューを開閉するアコーディオンをやむを得ず混在させる場合は、両者を明確に異なったアイコンを使用することが求められます。

- ただし、サイト内でのアイコンの仕様は挙動別に一貫性を保ってください。

#### 良い例

![スクリーンショット：エンドアイコンの付いたメニューリストの例。リンクを示唆するために右向きシェブロンの付いた項目と、サブメニューの開閉を示すプラス／マイナスの付いた項目が混在している。](https://design.digital.go.jp/dads/images/components/menu-list/overview/menu_list_cta_1.png)

リンクとアコーディオンという異なった機能を、明確に異なるアイコンで示しているため、挙動が違うことを想定できる。

#### 悪い例

![スクリーンショット：エンドアイコンの付いたメニューリストの例。リンクを示唆するために右向きのシェブロン、サブメニューの開閉を示すために上下を向いたシェブロンが使われている。](https://design.digital.go.jp/dads/images/components/menu-list/overview/menu_list_cta_2.png)

リンクとアコーディオンという異なった機能を、シェブロン（矢印アイコン）の向きの違いで表現しているため、ふたつの機能の混在を一目で把握するには認知負荷が高い。

### セクションの明確化

セクションをより明確にしたい場合は以下のUIを利用します。

- ディバイダー

  - ディバイダーを使用してセクションを大きく分割することが可能です。
  - 特にコンテンツ内容や機能の性質が大きく異なったセクションを分割する場合に適しています。

#### スタンダードなカテゴリータイトル

![スクリーンショット：2つのセクションからなるメニューリストの例。各セクションはセクション名が太字で表現され、通常の項目と判別できるようになっている。セクション間にはホワイトスペースが設けられ、セクションのまとまりが認知できるようになっている。](https://design.digital.go.jp/dads/images/components/menu-list/overview/menu_list_section_1.png)

#### ディバイダーを追加

![スクリーンショット：2つのセクションからなるメニューリストの例。各セクションはセクション名が太字で表現され、通常の項目と判別できるようになっている。セクション間にはディバイダーが配置され、セクションの区切りが明確になっている。](https://design.digital.go.jp/dads/images/components/menu-list/overview/menu_list_section_2.png)

## 各種リソース

| 種別       | リソース                                                                                                                                      | 状態  |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------- | --- |
| デザイン     | [Figmaデザインデータ（v2） \[新規タブで開きます\]](https://www.figma.com/community/file/1377880368787735577)                                                | 提供中 |
| HTML版実装  | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-html/tree/main/src/components/menu-list) | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/html/?path=/docs/components-メニューリスト--docs)                              | 提供中 |
| React版実装 | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-react/tree/main/src/components/MenuList) | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/react/?path=/docs/component-dads-v2-menulist--docs)                     | 提供中 |
