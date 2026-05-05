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
    if REPORTED_PATH.exists():
        data = json.loads(REPORTED_PATH.read_text())
        return set(data)
    return set()


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


def select_top_n(papers: list[dict], reported: set[str], top_n: int) -> list[dict]:
    unreported = [p for p in papers if _uid(p) not in reported and p.get("title")]
    scored = sorted(unreported, key=score_paper, reverse=True)
    return scored[:top_n]


# ---------- エントリポイント ----------

def fetch_and_select() -> tuple[list[dict], list[str]]:
    config = load_config()
    keywords: list[str] = config.get("keywords", [])
    max_results: int = config.get("max_results", 20)
    top_n: int = config.get("top_n", 3)
    reported = load_reported()

    all_papers: list[dict] = []
    for kw in keywords:
        print(f"[PubMed] 検索中: {kw}")
        try:
            all_papers.extend(search_pubmed(kw, max_results))
        except Exception as e:
            print(f"  PubMed エラー: {e}")
        time.sleep(0.5)

        print(f"[Semantic Scholar] 検索中: {kw}")
        try:
            all_papers.extend(search_semantic_scholar(kw, max_results))
        except Exception as e:
            print(f"  Semantic Scholar エラー: {e}")
        time.sleep(1)

    merged = merge_papers(all_papers)
    print(f"取得論文数（重複除去後）: {len(merged)}")

    top = select_top_n(merged, reported, top_n)
    new_uids = [_uid(p) for p in top]
    print(f"Top {top_n} 選出: {[p['title'][:60] for p in top]}")
    return top, new_uids


if __name__ == "__main__":
    papers, uids = fetch_and_select()
    for i, p in enumerate(papers, 1):
        print(f"\n--- #{i} ---")
        print(f"タイトル: {p['title']}")
        print(f"雑誌: {p['journal']} ({p['year']})")
        print(f"引用数: {p['citation_count']}")
        print(f"OA URL: {p['open_access_url']}")
