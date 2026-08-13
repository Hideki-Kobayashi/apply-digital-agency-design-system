---
title: "ドロワー 概要"
category: "components"
slug: "drawer"
document_type: "reference"
source_url: "https://design.digital.go.jp/dads/components/drawer/"
language: "ja"
---

# ドロワー （ 概要 ）

[2025年1月15日更新](changelog.md)

![スクリーンショット：モバイルメニューで構成されるドロワーの3つの展開パターン。](https://design.digital.go.jp/dads/images/components/drawer/overview/drawer_overview.png)

ブラウザ画面の四辺(上下左右端)から展開し、モバイルメニューなどのコンポーネントを格納可能なコンテナです。

## 仕様

ハンバーガーメニューボタンのような起点となるコンポーネントによって開閉が制御されます。展開パターンとして、全面オーバーレイ、右・左タイプのオーバーレイを用意しています。

- ドロワーは必ずモードを持ちます（モーダル）。
- ドロワーにはエレベーションが設定され、親要素はオーバーレイシェードで覆われます。ドロワー内部に配置されたコンテンツやリンク以外にはアクセスできません。
- 「閉じる」ボタンの押下によりドロワーを閉じることができます。

## 各種リソース

| 種別       | リソース                                                                                                                                    | 状態  |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------- | --- |
| デザイン     | [Figmaデザインデータ（v2） \[新規タブで開きます\]](https://www.figma.com/community/file/1377880368787735577)                                              | 提供中 |
| HTML版実装  | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-html/tree/main/src/components/drawer)  | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/html/?path=/docs/components-ドロワー--docs)                               | 提供中 |
| React版実装 | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-react/tree/main/src/components/Drawer) | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/react/?path=/docs/component-dads-v2-drawer--full-drawer)              | 提供中 |
