"""
PubMed と Semantic Scholar から論文を取得し、重複除去・スコアリングして
上位 top_n 件（未報告のもの）を返す。
"""

import json
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests
import yaml

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "config.yml"
REPORTED_PATH = ROOT / "data" / "reported.json"

PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
SEMANTIC_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_FIELDS = "paperId,externalIds,title,abstract,year,citationCount,openAccessPdf,authors,venue,url"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_reported() -> set[str]:
    """
    reported.json を読み込み、有効期限内（reported_expiry_days 以内）の DOI セットを返す。
    旧フォーマット（文字列リスト）にも対応。
    """
    if not REPORTED_PATH.exists():
        return set()

    config = load_config()
    expiry_days: int = config.get("reported_expiry_days", 90)
    cutoff = date.today().toordinal() - expiry_days

    raw = json.loads(REPORTED_PATH.read_text())
    reported: set[str] = set()
    for entry in raw:
        if isinstance(entry, str):
            # 旧フォーマット：DOI 文字列のみ → 報告日不明なので有効期限内とみなす
            reported.add(entry)
        elif isinstance(entry, dict):
            doi = entry.get("doi", "")
            reported_at_str = entry.get("reported_at", "")
            try:
                reported_date = date.fromisoformat(reported_at_str).toordinal()
                if reported_date >= cutoff:
                    reported.add(doi)
                # cutoff より古ければ除外（再候補になる）
            except (ValueError, TypeError):
                reported.add(doi)  # 日付不明は有効とみなす
    return reported


# ---------- PubMed ----------

def search_pubmed(keyword: str, max_results: int) -> list[dict]:
    params = {
        "db": "pubmed",
        "term": keyword,
        "retmax": max_results,
        "sort": "relevance",
        "retmode": "json",
    }
    r = requests.get(PUBMED_SEARCH, params=params, timeout=15)
    r.raise_for_status()
    ids = r.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []

    time.sleep(0.5)
    fetch_params = {
        "db": "pubmed",
        "id": ",".join(ids),
        "rettype": "xml",
        "retmode": "xml",
    }
    fr = requests.get(PUBMED_FETCH, params=fetch_params, timeout=30)
    fr.raise_for_status()
    return _parse_pubmed_xml(fr.text, keyword)


def _parse_pubmed_xml(xml_text: str, keyword: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    papers = []
    for article in root.findall(".//PubmedArticle"):
        try:
            medline = article.find("MedlineCitation")
            art = medline.find("Article")

            title_el = art.find("ArticleTitle")
            title = "".join(title_el.itertext()) if title_el is not None else ""

            abstract_el = art.find("Abstract/AbstractText")
            abstract = "".join(abstract_el.itertext()) if abstract_el is not None else ""

            pmid_el = medline.find("PMID")
            pmid = pmid_el.text if pmid_el is not None else ""

            doi = ""
            for id_el in article.findall(".//ArticleId"):
                if id_el.get("IdType") == "doi":
                    doi = id_el.text or ""
                    break

            pub_date = medline.find(".//PubDate")
            year = 0
            if pub_date is not None:
                year_el = pub_date.find("Year")
                if year_el is not None:
                    try:
                        year = int(year_el.text)
                    except (ValueError, TypeError):
                        year = 0

            authors = []
            for author in art.findall(".//Author"):
                last = author.findtext("LastName", "")
                fore = author.findtext("ForeName", "")
                name = f"{last} {fore}".strip()
                if name:
                    authors.append(name)

            journal_el = art.find("Journal/Title")
            journal = journal_el.text if journal_el is not None else ""

            papers.append({
                "doi": doi,
                "pmid": pmid,
                "title": title,
                "abstract": abstract,
                "year": year,
                "authors": authors,
                "journal": journal,
                "citation_count": 0,
                "open_access_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                "source": "pubmed",
                "keyword": keyword,
            })
        except Exception:
            continue
    return papers


# ---------- Semantic Scholar ----------

def search_semantic_scholar(keyword: str, max_results: int) -> list[dict]:
    params = {
        "query": keyword,
        "limit": max_results,
        "fields": SEMANTIC_FIELDS,
    }
    headers = {"User-Agent": "paper-tracker/1.0"}
    r = requests.get(SEMANTIC_SEARCH, params=params, headers=headers, timeout=20)
    if r.status_code == 429:
        time.sleep(5)
        r = requests.get(SEMANTIC_SEARCH, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json().get("data", [])
    papers = []
    for item in data:
        doi = (item.get("externalIds") or {}).get("DOI", "")
        pmid = str((item.get("externalIds") or {}).get("PubMed", ""))
        oa = item.get("openAccessPdf") or {}
        oa_url = oa.get("url", "")
        papers.append({
            "doi": doi,
            "pmid": pmid,
            "title": item.get("title", ""),
            "abstract": "",
            "year": item.get("year") or 0,
            "authors": [a.get("name", "") for a in (item.get("authors") or [])],
            "journal": item.get("venue", ""),
            "citation_count": item.get("citationCount") or 0,
            "open_access_url": oa_url,
            "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            "semantic_url": item.get("url", ""),
            "source": "semantic_scholar",
            "keyword": keyword,
        })
    return papers


# ---------- マージ・スコアリング ----------

def _uid(paper: dict) -> str:
    if paper.get("doi"):
        return paper["doi"].lower().strip()
    if paper.get("pmid"):
        return f"pmid:{paper['pmid']}"
    return paper["title"].lower()[:80]


def merge_papers(all_papers: list[dict]) -> list[dict]:
    """DOI / PMID で重複除去し、情報をマージする。"""
    merged: dict[str, dict] = {}
    for p in all_papers:
        uid = _uid(p)
        if uid not in merged:
            merged[uid] = p
        else:
            existing = merged[uid]
            if p.get("citation_count", 0) > existing.get("citation_count", 0):
                existing["citation_count"] = p["citation_count"]
            if p.get("open_access_url") and not existing.get("open_access_url"):
                existing["open_access_url"] = p["open_access_url"]
            if p.get("abstract") and not existing.get("abstract"):
                existing["abstract"] = p["abstract"]
            if p.get("semantic_url") and not existing.get("semantic_url"):
                existing["semantic_url"] = p["semantic_url"]
    return list(merged.values())


def score_paper(paper: dict) -> float:
    current_year = date.today().year
    year = paper.get("year") or (current_year - 10)
    recency = max(0, 1 - (current_year - year) / 20)
    citations = paper.get("citation_count", 0)
    citation_score = min(citations / 500, 1.0)
    oa_bonus = 0.2 if paper.get("open_access_url") else 0.0
    return citation_score * 0.4 + recency * 0.4 + oa_bonus


def select_top_n_per_keyword(
    papers_by_keyword: dict[str, list[dict]],
    reported: set[str],
    top_n: int,
) -> list[dict]:
    """キーワードごとに top_n 件ずつ選出して結合する。"""
    result = []
    for kw, papers in papers_by_keyword.items():
        unreported = [p for p in papers if _uid(p) not in reported and p.get("title")]
        scored = sorted(unreported, key=score_paper, reverse=True)
        selected = scored[:top_n]
        print(f"  [{kw}] Top {top_n} 選出: {[p['title'][:50] for p in selected]}")
        result.extend(selected)
    return result


def score_trending(paper: dict, cfg: dict) -> float:
    """直近1年・引用速度重視のスコアリング。"""
    cw = cfg.get("citation_weight", 0.2)
    rw = cfg.get("recency_weight", 0.6)
    vw = cfg.get("velocity_weight", 0.2)

    current_year = date.today().year
    year = paper.get("year") or (current_year - 10)
    recency = max(0, 1 - (current_year - year) / 5)  # 5年スケール（直近重視）

    citations = paper.get("citation_count", 0)
    citation_score = min(citations / 200, 1.0)  # 200件で満点（新しい論文向け）

    # 月あたり引用数（発表から今までの月数で割る）
    months_since = max(1, (current_year - year) * 12)
    velocity = min((citations / months_since) / 5, 1.0)  # 月5件で満点

    return citation_score * cw + recency * rw + velocity * vw


def search_pubmed_recent(keywords: list[str], max_results: int) -> list[dict]:
    """直近1年に絞った PubMed 検索（日付順）。"""
    from datetime import date as _date
    today = _date.today()
    mindate = f"{today.year - 1}/{today.month:02d}/{today.day:02d}"
    maxdate = today.strftime("%Y/%m/%d")
    query = " OR ".join(f'"{kw}"' for kw in keywords)
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "sort": "date",          # 日付の新しい順
        "datetype": "pdat",
        "mindate": mindate,
        "maxdate": maxdate,
        "retmode": "json",
    }
    r = requests.get(PUBMED_SEARCH, params=params, timeout=15)
    r.raise_for_status()
    ids = r.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []

    time.sleep(0.5)
    fetch_params = {
        "db": "pubmed",
        "id": ",".join(ids),
        "rettype": "xml",
        "retmode": "xml",
    }
    fr = requests.get(PUBMED_FETCH, params=fetch_params, timeout=30)
    fr.raise_for_status()
    # keyword タグを "trending" として記録
    papers = _parse_pubmed_xml(fr.text, "trending")
    return papers


def search_semantic_scholar_recent(keywords: list[str], max_results: int) -> list[dict]:
    """直近1年に絞った Semantic Scholar 検索。"""
    from datetime import date as _date
    year_from = _date.today().year - 1
    query = " OR ".join(keywords)
    params = {
        "query": query,
        "limit": max_results,
        "fields": SEMANTIC_FIELDS,
        "year": f"{year_from}-",   # year_from 以降
    }
    headers = {"User-Agent": "paper-tracker/1.0"}
    r = requests.get(SEMANTIC_SEARCH, params=params, headers=headers, timeout=20)
    if r.status_code == 429:
        time.sleep(5)
        r = requests.get(SEMANTIC_SEARCH, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    data = r.json().get("data", [])
    papers = []
    for item in data:
        doi = (item.get("externalIds") or {}).get("DOI", "")
        pmid = str((item.get("externalIds") or {}).get("PubMed", ""))
        oa = item.get("openAccessPdf") or {}
        oa_url = oa.get("url", "")
        papers.append({
            "doi": doi,
            "pmid": pmid,
            "title": item.get("title", ""),
            "abstract": "",
            "year": item.get("year") or 0,
            "authors": [a.get("name", "") for a in (item.get("authors") or [])],
            "journal": item.get("venue", ""),
            "citation_count": item.get("citationCount") or 0,
            "open_access_url": oa_url,
            "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            "semantic_url": item.get("url", ""),
            "source": "semantic_scholar",
            "keyword": "trending",
        })
    return papers


def select_trending(
    reported: set[str],
    already_selected_uids: set[str],
    cfg: dict,
    keywords: list[str],
) -> dict | None:
    """直近1年に絞った専用検索を行い、話題性スコア1位を選出する。"""
    max_results: int = cfg.get("max_results", 40)
    current_year = date.today().year
    cutoff_year = current_year - 1

    print("  [Trending] 直近1年の専用検索中...")
    trending_papers: list[dict] = []
    try:
        trending_papers.extend(search_pubmed_recent(keywords, max_results))
        print(f"    PubMed（直近1年）: {len(trending_papers)} 件")
    except Exception as e:
        print(f"    PubMed 直近検索エラー: {e}")
    time.sleep(0.5)
    try:
        ss_papers = search_semantic_scholar_recent(keywords, max_results)
        trending_papers.extend(ss_papers)
        print(f"    Semantic Scholar（直近1年）: {len(ss_papers)} 件")
    except Exception as e:
        print(f"    Semantic Scholar 直近検索エラー: {e}")

    merged = merge_papers(trending_papers)
    print(f"    重複除去後: {len(merged)} 件")

    candidates = [
        p for p in merged
        if p.get("title")
        and _uid(p) not in reported
        and _uid(p) not in already_selected_uids
        and (p.get("year") or 0) >= cutoff_year
    ]
    print(f"    未報告候補: {len(candidates)} 件")

    if not candidates:
        print("  [Trending] 直近1年の未報告論文なし")
        return None

    scored = sorted(candidates, key=lambda p: score_trending(p, cfg), reverse=True)
    best = scored[0]
    best["is_trending"] = True
    print(f"  [Trending] 選出: {best['title'][:60]}")
    return best


# ---------- エントリポイント ----------

def fetch_and_select() -> tuple[list[dict], list[str]]:
    config = load_config()
    keywords: list[str] = config.get("keywords", [])
    max_results: int = config.get("max_results", 20)
    top_n: int = config.get("top_n", 2)
    trending_cfg: dict = config.get("trending", {})
    reported = load_reported()

    # キーワードごとに論文を収集・重複除去
    papers_by_keyword: dict[str, list[dict]] = {}
    all_papers_flat: list[dict] = []
    for kw in keywords:
        kw_papers: list[dict] = []

        print(f"[PubMed] 検索中: {kw}")
        try:
            kw_papers.extend(search_pubmed(kw, max_results))
        except Exception as e:
            print(f"  PubMed エラー: {e}")
        time.sleep(0.5)

        print(f"[Semantic Scholar] 検索中: {kw}")
        try:
            kw_papers.extend(search_semantic_scholar(kw, max_results))
        except Exception as e:
            print(f"  Semantic Scholar エラー: {e}")
        time.sleep(1)

        merged_kw = merge_papers(kw_papers)
        print(f"  [{kw}] 取得論文数（重複除去後）: {len(merged_kw)}")
        papers_by_keyword[kw] = merged_kw
        all_papers_flat.extend(merged_kw)

    # 通常枠（キーワードごと top_n）
    top = select_top_n_per_keyword(papers_by_keyword, reported, top_n)
    selected_uids = {_uid(p) for p in top}

    # 5本目：Trending枠（専用検索・直近1年・引用速度重視）
    if trending_cfg.get("enabled", True):
        print("\n[Trending] 話題論文を選出中...")
        trending = select_trending(reported, selected_uids, trending_cfg, keywords)
        if trending:
            top.append(trending)

    new_uids = [_uid(p) for p in top]
    print(f"\n合計 {len(top)} 件選出完了")
    return top, new_uids


if __name__ == "__main__":
    papers, uids = fetch_and_select()
    for i, p in enumerate(papers, 1):
        print(f"\n--- #{i} ---")
        print(f"タイトル: {p['title']}")
        print(f"雑誌: {p['journal']} ({p['year']})")
        print(f"引用数: {p['citation_count']}")
        print(f"OA URL: {p['open_access_url']}")
