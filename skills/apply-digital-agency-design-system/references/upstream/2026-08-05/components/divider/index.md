---
title: "ディバイダー 概要"
category: "components"
slug: "divider"
document_type: "reference"
source_url: "https://design.digital.go.jp/dads/components/divider/"
language: "ja"
---

# ディバイダー （ 概要 ）

[2025年1月9日更新](changelog.md)

![スクリーンショット：コンテンツを区切っているディバイダー。](https://design.digital.go.jp/dads/images/components/divider/overview/divider_overview.png)

ディバイダーは、異なるセクション、コンポーネント、またはコンテンツのグループ間に設けられる視覚的な区切りです。要素間に明確な区切りを設けることで、読みやすさを向上させる役割を果たします。

## 使い方

### ディバイダータイプ

ディバイダーは全幅タイプとインセットタイプが使用されます。

全幅タイプはコンテンツエリア全幅の仕切りを構成し、セクションやリストを視覚的に明確に区別化します。またインタラクティブエリアとインタラクティブでないエリアを区別化します。

インセットタイプは関連する同セクション内でグループ化したい場合に適しています。全幅タイプに比べ、区別化すると同時にセクション内の関連性を維持しやすくします。

#### 全幅タイプ

![スクリーンショット：全幅タイプのディバイダー。コンテナを完全に横断する幅を持っている。](https://design.digital.go.jp/dads/images/components/divider/overview/divider_type_1.png)

#### インセットタイプ

![スクリーンショット：インセットタイプのディバイダー。コンテナに対してパディングを除く領域を埋めるだけの幅を持っている。](https://design.digital.go.jp/dads/images/components/divider/overview/divider_type_2.png)

### マージン

リストで使用する時は8px以上、セクションで使用する時は16px以上の十分な余白を取ることを心がけてください。

余白をしっかり取って、視覚的にコンテンツグループや機能性を整頓することで、可読性や視認性を高め、誤読のリスクを軽減します。

また、ディバイダーは、余白をより明確にするための視覚的な補助ですので、ディバイダーなしで文意が伝わらないようなコンテンツ構成にしてはなりません。

#### 悪い例

![スクリーンショット：いくつかの単一行テキストがディバイダーで区切られている。ディバイダーとテキストの余白がほとんど確保されていない。](https://design.digital.go.jp/dads/images/components/divider/overview/divider_margin_2.png)

余白が十分でないと、複数項目がひとかたまりの情報として認識されてしまいます。

#### 良い例

![スクリーンショット：いくつかの単一行テキストがディバイダーで区切られている。ディバイダーとテキストの余白が1em程度確保されている。](https://design.digital.go.jp/dads/images/components/divider/overview/divider_margin_1.png)

余白を十分に取り、ディバイダーが補足的に使用されることで、情報が一目で複数項目として認識できます。

#### 悪い例

![スクリーンショット：2つの複数行テキストがディバイダーで区切られている。ディバイダーの上下の余白は0.5em程度だけ確保されている。](https://design.digital.go.jp/dads/images/components/divider/overview/divider_margin_4.png)

余白が十分でないため、ディバイダーの前後の情報が一つのグループであるかのように見えてしまいます。

#### 良い例

![スクリーンショット：2つの複数行テキストがディバイダーで区切られている。ディバイダーの上下の余白は2em程度確保されている。](https://design.digital.go.jp/dads/images/components/divider/overview/divider_margin_3.png)

余白を十分に取り、情報が二つのグループに分かれていることを明確にして可読性を高めています。

## 各種リソース

| 種別       | リソース                                                                                                                                     | 状態  |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------- | --- |
| デザイン     | [Figmaデザインデータ（v2） \[新規タブで開きます\]](https://www.figma.com/community/file/1377880368787735577)                                               | 提供中 |
| HTML版実装  | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-html/tree/main/src/components/divider)  | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/html/?path=/docs/components-ディバイダー--docs)                              | 提供中 |
| React版実装 | [ソースコード（GitHub） \[新規タブで開きます\]](https://github.com/digital-go-jp/design-system-example-components-react/tree/main/src/components/Divider) | 提供中 |
|          | [サンプル（Storybook） \[新規タブで開きます\]](https://design.digital.go.jp/dads/react/?path=/docs/component-dads-v2-divider--docs)                     | 提供中 |
