---
status: active
last_verified: 2026-08-12
source_of_truth:
  - source-manifest.json
---

# 作業別の参照索引

この索引は、利用者の依頼から読む公式文書を選ぶために使う。
設計ルールの正本は、`source-manifest.json`が示す有効スナップショット内のデジタル庁デザインシステム文書である。

## 文書の識別

- 各文書の正本IDには、Front Matterの`source_url`を使う。
- `slug`は本文と更新履歴で重複するため、文書IDとして使わない。
- 表内のパスは、有効スナップショットからの相対パスである。
- ファイルの列挙に`MANIFEST.md`を使わない。
  有効スナップショット内の全Markdownを走査する。
- `document_type: reference`を現行の参照文書として使う。
- 更新差分を尋ねられた場合だけ、対応する`document_type: changelog`も読む。

## 基本デザイン

画面全体を新しく設計するときは8文書をすべて検討する。
部分的な修正では、タスク別ルーティングが指定する分類だけを追加する。

| 分類 | 検索語 | 参照文書 | 正本ID |
|---|---|---|---|
| カラー | 色、配色、背景色、コントラスト、状態色、エラー、警告、成功、フォーカス、ハイライト | `foundations/color/index.md` | `https://design.digital.go.jp/dads/foundations/color/` |
| タイポグラフィ | 書体、フォント、文字サイズ、太さ、行間、行高、テキストスタイル、読みやすさ | `foundations/typography/index.md` | `https://design.digital.go.jp/dads/foundations/typography/` |
| アイコン | アイコン、SVG、ピクトグラム、代替テキスト、ラベル、アイコン単体 | `foundations/icon/index.md` | `https://design.digital.go.jp/dads/foundations/icon/` |
| レイアウト | グリッド、カラム、レスポンシブ、ブレークポイント、画面幅、読み上げ順 | `foundations/layout/index.md` | `https://design.digital.go.jp/dads/foundations/layout/` |
| リンクテキスト | リンク、アンカー、新規タブ、外部リンク、ダウンロード、「こちら」、クリック領域 | `foundations/link-text/index.md` | `https://design.digital.go.jp/dads/foundations/link-text/` |
| 余白 | 余白、間隔、マージン、パディング、gap、グループ化、階層 | `foundations/spacing/index.md` | `https://design.digital.go.jp/dads/foundations/spacing/` |
| 角の形状 | 角丸、radius、形状、強調、カードの角、ボタンの角 | `foundations/corner-shapes/index.md` | `https://design.digital.go.jp/dads/foundations/corner-shapes/` |
| エレベーション | 影、シャドウ、重なり、オーバーレイ、モーダル、ドロップダウン、z-index、背景遮蔽 | `foundations/elevation/index.md` | `https://design.digital.go.jp/dads/foundations/elevation/` |

## タスク別ルーティング

表の「基本デザイン」は、上の8分類を指す。

| 検索語または依頼 | 主に読む文書 | 追加する基本デザイン |
|---|---|---|
| 新規サイト、画面全体、デザイン方針、スタイルガイド、ブランドへの適用 | `guidance/style-guides/index.md`、`guidance/how-to-use/index.md` | 8分類すべて |
| 見出し、本文、箇条書き、定義一覧、引用、区切り、カード、記事一覧、資料一覧 | `components/heading/index.md`、`components/list/index.md`、`components/description-list/index.md`、`components/blockquote/index.md`、`components/divider/index.md`、`components/card/index.md`、`components/resource-list/index.md` | タイポグラフィ、余白、レイアウト、リンクテキスト。カードには角の形状も追加 |
| ボタン、CTA、送信、確定、キャンセル、戻る、主要操作、disabled | `components/button/index.md` | カラー、余白、タイポグラフィ、アイコン、角の形状 |
| フォーム、入力欄、氏名、メール、長文、選択、複数選択、単一選択、日付、アップロード、即時切替 | `components/input-text/index.md`、`components/textarea/index.md`、`components/select/index.md`、`components/checkbox/index.md`、`components/radio/index.md`、`components/combobox/index.md`、`components/date-picker/index.md`、`components/file-upload/index.md`、`components/switch/index.md`、`components/button/index.md` | レイアウト、余白、タイポグラフィ、カラー、アイコン |
| 検索、絞り込み、フィルター、候補補完、タグ入力、テーブル操作 | `components/search-box/index.md`、`components/combobox/index.md`、`components/table-control/index.md`、`components/chip-tag/index.md` | レイアウト、余白、カラー、アイコン |
| ヘッダー、グローバルナビ、メニュー、ハンバーガー、モバイルメニュー、ドロワー、メガメニュー | `components/header-container/index.md`、`components/horizontal-menu/index.md`、`components/hamburger-menu-button/index.md`、`components/mobile-menu/index.md`、`components/drawer/index.md`、`components/mega-menu/index.md`、`components/menu-list/index.md`、`components/menu-list-box/index.md` | レイアウト、余白、リンクテキスト、アイコン、カラー、エレベーション |
| パンくず、ページ送り、ステップ、ウィザード、目次、ボトムナビ、補助リンク、言語切替、先頭へ戻る、フッター | `components/breadcrumb/index.md`、`components/page-navigation/index.md`、`components/step-navigation/index.md`、`components/toc/index.md`、`components/bottom-navigation/index.md`、`components/utility-link/index.md`、`components/language-selector/index.md`、`components/scroll-top-button/index.md` | レイアウト、余白、リンクテキスト、アイコン |
| お知らせ、補足、注意、警告、エラー、成功、状態、ラベル、進捗、処理中、緊急情報 | `components/notice-block/index.md`、`components/notification-banner/index.md`、`components/emergency-banner/index.md`、`components/chip-label/index.md`、`components/progress-indicator/index.md` | カラー、タイポグラフィ、余白、アイコン |
| 折りたたみ、詳細表示、アコーディオン、タブ、モーダル、ダイアログ、オーバーレイ | `components/accordion/index.md`、`components/disclosure/index.md`、`components/tab/index.md`、`components/modal-dialog/index.md`、`components/drawer/index.md` | エレベーション、カラー、余白、レイアウト、アイコン |
| 表、データ一覧、比較表、行列、並べ替え、データ操作 | `components/table/index.md`、`components/table-control/index.md` | タイポグラフィ、レイアウト、余白、カラー、リンクテキスト |
| 画像、写真、図、キャプション、ギャラリー、スライダー、カルーセル | `components/image/index.md`、`components/image-slider/index.md`、`components/carousel/index.md` | レイアウト、余白、タイポグラフィ |
| アクセシビリティ、WCAG、WAI-ARIA、キーボード、スクリーンリーダー、フォーカス | `guidance/accessibility/index.md`と、対象の基本デザインおよびコンポーネント文書 | 対象に応じて選ぶ |
| デジタル庁デザインシステムサイト自身の適合試験、試験結果、対象ページ | `webaccessibility/index.md`、`webaccessibility/result/index.md`、`webaccessibility/page-list/index.md` | なし。一般製品の設計規則として流用しない |
| ライセンス、出典、利用条件、Figmaやコードの扱い | `introduction/notices/index.md` | なし |

## 更新履歴へのルーティング

変更点、旧版との差、更新日、Revを尋ねられた場合は、次の順で読む。

1. 対象の`index.md`を読む。
2. 同じディレクトリに`changelog.md`があれば読む。
3. 文書更新は`updates/updates-dads/index.md`を読む。
4. Figma版は`updates/updates-design/index.md`を読む。
5. 実装例は`updates/updates-code-snippet/index.md`を読む。
6. Markdownアーカイブ自体は`updates/updates-misc/index.md`と`resources/index.md`を読む。

更新履歴の関連付けには、`slug`ではなく次を使う。

- 現行文書：Front Matterの`source_url`。
- ローカル上の組：同じディレクトリの`index.md`と`changelog.md`。
- 文書種別：`document_type`。

## 該当文書が見つからない場合

1. `search_guidance.py`で、依頼語と同義語を空白区切りで検索する。
2. `document_type: reference`の文書を優先する。
3. 見つからないコンポーネントや規則を、デジタル庁デザインシステムの仕様として作らない。
4. ローカル版に十分な記述がない場合は、対象文書の`source_url`を公式確認先として示し、未確認事項として報告する。
