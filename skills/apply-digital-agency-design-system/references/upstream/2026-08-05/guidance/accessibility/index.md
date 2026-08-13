---
title: "アクセシビリティ"
category: "guidance"
slug: "accessibility"
document_type: "reference"
source_url: "https://design.digital.go.jp/dads/guidance/accessibility/"
language: "ja"
---

# アクセシビリティ

[2025年10月29日更新](changelog.md)

デジタル庁デザインシステムはアクセシビリティを最優先事項として作成されています。アクセシビリティは、すべてのユーザーがウェブサイトやオンラインサービスを確実に利用できるようにするための品質基準であり、企画・設計からデザイン、開発、およびコンテンツ作成、そして運用など、プロセスのすべてにおいて考慮が必要となる概念です。ここでは、デザインシステムとアクセシビリティの関係について説明します。

## デジタル庁デザインシステムとアクセシビリティの関係

デジタル庁デザインシステムは、以下に関して特に注意を払って構築されており、アクセシビリティ規格において該当する達成基準の適合を容易にします。基本デザインやコンポーネントのFigmaデザインデータだけではなく、デザインシステム本体に含まれるコンポーネント仕様、作例、アクセシビリティガイドライン等にも等しく反映されています。

- 色の組み合わせとコントラスト比
- フォントサイズ
- キーボード操作、フォーカスインジケーター
- リンクやボタン等のターゲットサイズ
- 操作に対応したインタラクション表現
- 動きのあるオブジェクトの扱い
- 大きさの可変や内容量の増減を踏まえた外観構造

一方で、デザインシステムを利用して開発されるウェブサイトが独自にもつコンテンツ自体のアクセシビリティは、各ウェブサイトの制作者の側にて確保する必要があります。また、ウェブサイトのアクセシビリティが継続的に確保された状態を維持するためには、アクセシビリティを踏まえたコンテンツ運用設計と、それを実現するための予算や人材の調達が不可欠なものとなります。

### JIS X 8341-3:2016、WCAG、WAI-ARIA等の各ガイドライン

デジタル庁デザインシステムが参照しているアクセシビリティの基準は、WCAGやWAI-ARIAといったアクセシビリティに関する国際的な勧告です。WCAGの最新バージョンは2.2で、2.0はJIS X 8341-3:2016と互換性があります。

- [Web Content Accessibility Guidelines (WCAG) 2.2 勧告（日本語訳）](https://waic.jp/translations/WCAG22/)
- [W3C Accessibility Guidelines (WCAG) 3.0 ワーキングドラフト（英語）](https://www.w3.org/TR/wcag-3.0/)
- [Accessible Rich Internet Applications (WAI-ARIA) 1.2 勧告（英語）](https://www.w3.org/TR/wai-aria-1.2/)
- [Accessible Rich Internet Applications (WAI-ARIA) 1.3 ワーキングドラフト（英語）](https://www.w3.org/TR/wai-aria-1.3/)
- Web Content Accessibility Guidelines (WCAG) 2.1 勧告
- [JIS X 8341-3:2016 高齢者・障害者等配慮設計指針―情報通信における機器，ソフトウェア及びサービス―第３部：ウェブコンテンツ | 日本規格協会 JSA Group Webdesk](https://webdesk.jsa.or.jp/books/W11M0090/index/?bunsyo_id=JIS+X+8341-3%3A2016)
- Web Content Accessibility Guidelines (WCAG) 2.0 勧告
- [ARIA Authoring Practices Guide (APG)（英語）](https://www.w3.org/WAI/ARIA/apg/)

デザインシステムによって達成できるアクセシビリティは、考慮すべきアクセシビリティ全体の一部であることに留意してください。

#### \[インフォメーション]障害を理由とする差別の解消の推進に関する法律（改正法 2024年4月1日施行）

[改正障害者差別解消法](https://www8.cao.go.jp/shougai/suishin/law_h25-65.html)では、義務である合理的配慮の提供に先立ち、事前的改善措置として環境の整備（バリアフリー化、意思表示やコミュニケーションを支援するための人的支援、情報アクセシビリティの向上等）を努力義務として求めており、ウェブサイトにおいてはアクセシビリティの確保がこれに該当します。このほか、[障害者の権利に関する条約（障害者権利条約）](https://www.mofa.go.jp/mofaj/gaiko/jinken/index_shogaisha.html)第九条1(b)・2(g)および第二十一条(a)(c)、[障害者基本法](https://www8.cao.go.jp/shougai/suishin/kihonhou/s45-84.html) 第二十二条 2、[障害者基本計画 第3次計画](https://www8.cao.go.jp/shougai/suishin/kihonkeikaku25.html) 6.(1)および(4) 等でもウェブアクセシビリティの確保を求めています。

### そのほかのガイドライン等

デジタル庁デザインシステムは、アクセシビリティ確保に寄与するガイドラインや関連技術等も積極的に参照しています。

- [HTML Standard（英語）](https://html.spec.whatwg.org/multipage/)
- [Cascading Style Sheets（英語）](https://www.w3.org/Style/CSS/)
- [カラーユニバーサルデザイン推奨配色セット](https://jfly.uni-koeln.de/colorset/)
