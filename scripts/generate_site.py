"""
論文データ（JSON）から GitHub Pages 用の静的HTMLを生成する。
"""

import json
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"

IMPORTANCE_LABEL = {
    "high": ("重要", "#ef4444"),
    "medium": ("注目", "#f59e0b"),
    "low": ("参考", "#6b7280"),
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Paper Tracker</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <style>
    body {{ font-family: -apple-system, 'Hiragino Sans', sans-serif; }}
    .mermaid svg {{ max-width: 100%; height: auto; }}
  </style>
</head>
<body class="bg-gray-50 min-h-screen">
  <header class="bg-white border-b border-gray-200 sticky top-0 z-10 shadow-sm">
    <div class="max-w-3xl mx-auto px-4 py-3 flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold text-gray-900">Paper Tracker</h1>
        <p class="text-xs text-gray-500 mt-0.5">最終更新: {updated_at}</p>
      </div>
      <div class="flex gap-2 flex-wrap justify-end">
        {keyword_badges}
      </div>
    </div>
  </header>

  <main class="max-w-3xl mx-auto px-4 py-6 space-y-6">
    <div class="bg-white rounded-xl border border-gray-200 px-5 py-3 flex items-center gap-3">
      <span class="text-2xl font-bold text-indigo-600">{date_str}</span>
      <span class="text-gray-500">の注目論文（キーワードごと Top {top_n}）</span>
    </div>

    {paper_cards}

    <div class="text-center py-8">
      <a href="history.html" class="text-indigo-600 hover:underline text-sm">過去の報告を見る →</a>
    </div>
  </main>

  <script>
    mermaid.initialize({{ startOnLoad: true, theme: 'neutral', securityLevel: 'loose' }});
  </script>
</body>
</html>"""

PAPER_CARD_TEMPLATE = """
<article class="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
  <div class="px-5 py-4 border-b border-gray-100 flex items-start gap-3">
    <span class="text-2xl font-black text-indigo-200 leading-none mt-1">#{rank}</span>
    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-2 mb-1 flex-wrap">
        <span class="text-xs font-semibold px-2 py-0.5 rounded-full text-white" style="background:{importance_color}">{importance_label}</span>
        <span class="text-xs text-gray-400">{keyword_tag}</span>
      </div>
      <h2 class="text-base font-bold text-gray-900 leading-snug">{title}</h2>
      <p class="text-xs text-gray-500 mt-1">{journal_line}</p>
    </div>
  </div>

  <div class="px-5 py-4 border-b border-gray-100">
    <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">要約</h3>
    <p class="text-sm text-gray-700 leading-relaxed">{summary}</p>
  </div>

  {mermaid_section}

  <div class="px-5 py-4 border-b border-gray-100">
    <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">ポイント</h3>
    <ol class="space-y-2">
      {point_items}
    </ol>
  </div>

  <div class="px-5 py-4 flex gap-3 flex-wrap">
    {link_buttons}
  </div>
</article>"""

MERMAID_SECTION_TEMPLATE = """
  <div class="px-5 py-4 border-b border-gray-100 bg-gray-50">
    <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">メカニズム図</h3>
    <div class="mermaid text-sm overflow-x-auto">
{mermaid_code}
    </div>
  </div>"""

HISTORY_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>過去の報告 - Paper Tracker</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen">
  <header class="bg-white border-b border-gray-200 sticky top-0 z-10 shadow-sm">
    <div class="max-w-3xl mx-auto px-4 py-3">
      <a href="index.html" class="text-indigo-600 text-sm hover:underline">← 最新に戻る</a>
      <h1 class="text-xl font-bold text-gray-900 mt-1">過去の報告</h1>
    </div>
  </header>
  <main class="max-w-3xl mx-auto px-4 py-6 space-y-3">
    {history_items}
  </main>
</body>
</html>"""


def _escape(text: str) -> str:
    return (text or "")


def _render_keyword_badges(keywords: list[str]) -> str:
    colors = ["bg-indigo-100 text-indigo-700", "bg-pink-100 text-pink-700",
              "bg-teal-100 text-teal-700", "bg-orange-100 text-orange-700"]
    badges = []
    for i, kw in enumerate(keywords):
        color = colors[i % len(colors)]
        badges.append(f'<span class="text-xs font-medium px-2 py-1 rounded-full {color}">{kw}</span>')
    return "\n        ".join(badges)


def _render_paper_card(paper: dict, rank: int) -> str:
    imp = paper.get("ai_importance", "medium")
    imp_label, imp_color = IMPORTANCE_LABEL.get(imp, ("参考", "#6b7280"))

    journal = paper.get("journal", "")
    year = paper.get("year", "")
    citations = paper.get("citation_count", 0)
    journal_parts = [j for j in [journal, str(year) if year else ""] if j]
    if citations:
        journal_parts.append(f"引用 {citations}")
    journal_line = " | ".join(journal_parts)

    points = paper.get("ai_points", [])
    point_items = ""
    for j, pt in enumerate(points[:3], 1):
        if pt:
            point_items += f'<li class="flex gap-2 text-sm text-gray-700"><span class="font-bold text-indigo-500 shrink-0">[{j}]</span><span>{_escape(pt)}</span></li>\n      '

    mermaid_code = (paper.get("ai_mermaid") or "").strip()
    if mermaid_code:
        mermaid_section = MERMAID_SECTION_TEMPLATE.format(mermaid_code=mermaid_code)
    else:
        mermaid_section = ""

    links = []
    oa_url = paper.get("open_access_url", "")
    pubmed_url = paper.get("pubmed_url", "")
    semantic_url = paper.get("semantic_url", "")
    doi = paper.get("doi", "")

    if oa_url:
        links.append(f'<a href="{oa_url}" target="_blank" rel="noopener" class="inline-flex items-center gap-1 text-sm font-medium bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 transition">PDF 全文を読む →</a>')
    if pubmed_url and pubmed_url != oa_url:
        links.append(f'<a href="{pubmed_url}" target="_blank" rel="noopener" class="inline-flex items-center gap-1 text-sm font-medium border border-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-50 transition">PubMed →</a>')
    if semantic_url:
        links.append(f'<a href="{semantic_url}" target="_blank" rel="noopener" class="inline-flex items-center gap-1 text-sm font-medium border border-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-50 transition">Semantic Scholar →</a>')
    if doi and not pubmed_url and not oa_url:
        doi_url = f"https://doi.org/{doi}"
        links.append(f'<a href="{doi_url}" target="_blank" rel="noopener" class="inline-flex items-center gap-1 text-sm font-medium border border-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-50 transition">DOI →</a>')

    link_buttons = "\n    ".join(links) if links else '<span class="text-xs text-gray-400">リンクなし</span>'

    return PAPER_CARD_TEMPLATE.format(
        rank=rank,
        importance_color=imp_color,
        importance_label=imp_label,
        keyword_tag=paper.get("keyword", ""),
        title=_escape(paper.get("title", "")),
        journal_line=_escape(journal_line),
        summary=_escape(paper.get("ai_summary", paper.get("abstract", "")[:200])),
        mermaid_section=mermaid_section,
        point_items=point_items,
        link_buttons=link_buttons,
    )


def generate_index(papers: list[dict], keywords: list[str]) -> str:
    today = date.today()
    date_str = today.strftime("%Y年%m月%d日")
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M JST")
    keyword_badges = _render_keyword_badges(keywords)
    cards = "\n".join(_render_paper_card(p, i + 1) for i, p in enumerate(papers))
    return HTML_TEMPLATE.format(
        updated_at=updated_at,
        date_str=date_str,
        top_n=len(papers),
        keyword_badges=keyword_badges,
        paper_cards=cards,
    )


def generate_history(data_dir: Path) -> str:
    items = []
    json_files = sorted(data_dir.glob("20*.json"), reverse=True)
    for jf in json_files:
        try:
            papers = json.loads(jf.read_text())
            date_label = jf.stem
            titles = [p.get("title", "")[:60] for p in papers[:3]]
            title_list = "".join(f'<li class="text-sm text-gray-600 truncate">• {t}</li>' for t in titles)
            items.append(f"""
<div class="bg-white rounded-xl border border-gray-200 px-5 py-4">
  <p class="font-semibold text-gray-800 mb-2">{date_label}</p>
  <ul class="space-y-1">{title_list}</ul>
</div>""")
        except Exception:
            continue

    if not items:
        items = ['<p class="text-gray-400 text-center py-8">まだ履歴がありません。</p>']

    return HISTORY_TEMPLATE.format(history_items="\n".join(items))


def save_results(papers: list[dict]) -> None:
    today_str = date.today().isoformat()
    out_path = DATA_DIR / f"{today_str}.json"
    out_path.write_text(json.dumps(papers, ensure_ascii=False, indent=2))
    print(f"データ保存: {out_path}")


def build_site(papers: list[dict], keywords: list[str]) -> None:
    DOCS_DIR.mkdir(exist_ok=True)

    index_html = generate_index(papers, keywords)
    (DOCS_DIR / "index.html").write_text(index_html, encoding="utf-8")
    print("index.html 生成完了")

    history_html = generate_history(DATA_DIR)
    (DOCS_DIR / "history.html").write_text(history_html, encoding="utf-8")
    print("history.html 生成完了")


if __name__ == "__main__":
    import yaml
    with open(ROOT / "config.yml") as f:
        cfg = yaml.safe_load(f)
    keywords = cfg.get("keywords", [])

    today_file = DATA_DIR / f"{date.today().isoformat()}.json"
    if today_file.exists():
        papers = json.loads(today_file.read_text())
        build_site(papers, keywords)
    else:
        print("今日の論文データが見つかりません。先に run.py を実行してください。")
