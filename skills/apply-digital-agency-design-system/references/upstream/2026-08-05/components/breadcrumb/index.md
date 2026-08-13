---
title: "パンくずリスト 概要"
category: "components"
slug: "breadcrumb"
document_type: "reference"
source_url: "https://design.digital.go.jp/dads/components/breadcrumb/"
language: "ja"
---

# パンくずリスト （ 概要 ）

[2025年1月9日更新](changelog.md)

![スクリーンショット：パンくずリスト](https://design.digital.go.jp/dads/images/components/breadcrumb/overview/breadcrumb_overview.png)

パンくずリストは、ウェブサイトの階層内でユーザーの現在の位置を表示します。

## 使い方

### 配置と仕様

パンくずリストはヘッダーとページ見出しの間に配置されます。パンくずリストの長さは、当該ページのサイト構造上の階層の深さや、ページ見出しの文字長に依存し制御できないため、コンテンツエリア幅より広くなることを考慮して、改行する仕様を前提とします。

モバイルの場合は、デスクトップと同様に改行する仕様を使うか、または改行無しの横スクロールが可能な仕様を併用するかのどちらかで実装します。

#### デスクトップ

![スクリーンショット：パンくずリストがコンテンツ幅よりも長い場合、リンクテキストの途中で改行されている。](https://design.digital.go.jp/dads/images/components/breadcrumb/overview/breadcrumb_desktop.png)

パンくずリストがコンテンツ幅よりも長い場合は改行されます。

#### モバイル

##### 改行での仕様　（ページ上部に配置）

![スクリーンショット：ページ上部に配置されているパンくずリスト（改行あり）](https://design.digital.go.jp/dads/images/components/breadcrumb/overview/breadcrumb_mobile_1.png)

##### 改行での仕様　（ページ下部に配置）

![スクリーンショット：ページ下部に配置されているパンくずリスト（改行あり）](https://design.digital.go.jp/dads/images/components/breadcrumb/overview/breadcrumb_mobile_2.png)

改行仕様の場合はページ上部、またはページ下部にパンくずリストを配置します。

##### 横スクロールでの仕様

![スクリーンショット：ページ上部および下部に配置されているパンくずリスト。上部のパンくずリストは横スクロールで表示されるよう模式的に表現されている。下部のパンくずリストは改行されている。](https://design.digital.go.jp/dads/images/components/breadcrumb/overview/breadcrumb_mobile_3.png)

多くのページで長いパンくずリストが想定される場合、パンくずリストによってコンテンツを押し下げられることを防ぐため、改行無しの横スクロールによって閲覧できる仕様で実装します。ただし、横スクロールの仕様で実装した場合はページ下部、フッターエリアの上部に改行仕様のパンくずリストを配置するようにして下さい。

## 各種リソース

| 種別       | リソース                                                                                                                                         | 状態  |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------- | --- |
| デザイン     | [Figmaデザインデータ（v2） \[新規タブで開きます\]](https://www.figma.com/community/file/1377880368787735577)                                                   | 提供中 |
| HTML版実装  | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-html/tree/main/src/components/breadcrumb)   | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/html/?path=/docs/components-パンくずリスト--docs)                                 | 提供中 |
| React版実装 | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-react/tree/main/src/components/Breadcrumbs) | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/react/?path=/docs/component-dads-v2-breadcrumbs--docs)                     | 提供中 |
