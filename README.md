# tech-blog-feeds

国内外の技術ブログ（Webエンジニアリング学習用の一覧に載せた41ブログ）の新着記事を、毎日集めて `data/latest.json` にまとめるリポジトリです。

- `feeds.json` … 対象ブログの名前・区分・サイトURL・フィードURL。ブログを増やすときはここに1行足すだけ。
- `scripts/fetch_feeds.py` … RSS / Atom を取得して直近30日分を書き出す（標準ライブラリのみ）。フィードURLが変わっていた場合は、サイトのHTMLからフィードを探し直します。
- `.github/workflows/fetch.yml` … 毎日 06:17（日本時間）に実行し、変化があればコミットします。Actions タブの「Run workflow」で手動実行もできます。

`data/latest.json` は、Claude の予定タスクが毎朝読み込み、「技術ブログ新着チェック」ページに反映します。

## data/latest.json の形

```json
{
  "generatedAt": "2026-11-15T21:17:30Z",
  "days": 30,
  "feeds": [{"name": "…", "ok": true, "count": 5, "feedUrl": "…", "error": ""}],
  "items": [{"id": "md5(url)の先頭16桁", "blog": "…", "category": "国内企業", "title": "…", "url": "…", "publishedAt": "…Z", "summary": "…"}]
}
```

ローカルで試すとき: `python3 scripts/fetch_feeds.py 30`
