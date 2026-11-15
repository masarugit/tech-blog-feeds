"""data/latest.json から「技術ブログ新着チェック」ページのDBへ書き込む ops を作る。

usage: python3 build_import.py LATEST.json KNOWN_IDS.json OUTDIR
  KNOWN_IDS.json … DB の meta/ids ドキュメントの data（{"ids": [...]}、無ければ {} ）
OUTDIR に次を書き出す:
  articles_N.json … まだ無い記事の merge ops（50件ずつ）
  ids.json        … meta/ids に書く data（今回の latest.json に載っている id 一覧）
  status.json     … meta/status に書く data（取得状況とブログ一覧）
"""
import json
import sys
from pathlib import Path


def main():
    latest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    known_doc = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8") or "{}")
    outdir = Path(sys.argv[3])
    outdir.mkdir(parents=True, exist_ok=True)
    feeds_cfg = json.loads((Path(__file__).resolve().parent.parent / "feeds.json").read_text(encoding="utf-8"))

    known = set(known_doc.get("ids", []))
    ops = []
    for it in latest["items"]:
        if it["id"] in known:
            continue
        data = {k: v for k, v in it.items() if k != "id"}
        ops.append({"op": "merge", "path": "articles/" + it["id"], "data": data})
    for old in outdir.glob("articles_*.json"):
        old.unlink()
    for n in range(0, len(ops), 50):
        (outdir / f"articles_{n // 50}.json").write_text(json.dumps(ops[n:n + 50], ensure_ascii=False), encoding="utf-8")

    ids = sorted({it["id"] for it in latest["items"]})
    (outdir / "ids.json").write_text(json.dumps({"ids": ids}), encoding="utf-8")

    ok = {f["name"]: f for f in latest["feeds"]}
    blogs = []
    for f in feeds_cfg:
        st = ok.get(f["name"], {})
        blogs.append({"name": f["name"], "category": f["category"], "url": f["site"], "auto": bool(st.get("ok"))})
    n_ok = sum(1 for b in blogs if b["auto"])
    status = {
        "lastUpdated": latest["generatedAt"],
        "note": f"毎朝、{n_ok}ブログのRSSをGitHub Actionsで集めています。",
        "blogs": blogs,
    }
    (outdir / "status.json").write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    print(f"{len(ops)} new articles in {len(range(0, len(ops), 50))} files; {len(ids)} ids; {n_ok}/{len(blogs)} feeds ok")


main()
