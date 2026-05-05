"""
Gemini API を使って各論文の要約・メカニズム図（Mermaid）・ポイント3つを生成する。
"""

import json
import os
import time
from pathlib import Path

import google.generativeai as genai

MODEL_NAME = "gemini-2.0-flash"
GENERATION_CONFIG = {
    "temperature": 0.3,
    "max_output_tokens": 1500,
}

SYSTEM_PROMPT = """あなたは医学・生命科学の論文を日本語でわかりやすく解説する専門家です。
論文情報を受け取り、必ず以下のJSON形式のみで回答してください。余分なテキストは一切含めないでください。

{
  "summary": "3文以内の日本語要約。この研究が何をして何がわかったかを簡潔に。",
  "points": [
    "ポイント1（具体的な発見・手法）",
    "ポイント2（重要な結果・数値）",
    "ポイント3（臨床・研究上の意義）"
  ],
  "mermaid": "flowchart LR\\n    ...",
  "importance": "high または medium または low（この研究分野への重要度）"
}

mermaidフィールドは論文のメカニズムや発見を示すMermaid.jsのflowchartコードを書いてください。
ノード名にスペースや特殊文字を使う場合は必ず引用符で囲んでください。
例: flowchart LR\\n    A[\\"ドナー細胞\\"] -->|\\"ミトコンドリア移植\\"| B[\\"損傷細胞\\"]\\n    B --> C[\\"ATP産生回復\\"]
"""


def _setup_gemini() -> genai.GenerativeModel:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY 環境変数が設定されていません")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        generation_config=GENERATION_CONFIG,
        system_instruction=SYSTEM_PROMPT,
    )


def _build_prompt(paper: dict) -> str:
    title = paper.get("title", "（タイトル不明）")
    abstract = paper.get("abstract", "（アブストラクト未取得）")
    authors = ", ".join(paper.get("authors", [])[:3])
    journal = paper.get("journal", "")
    year = paper.get("year", "")
    return f"""以下の論文を解説してください。

タイトル: {title}
著者: {authors}
雑誌: {journal} ({year})
アブストラクト:
{abstract}
"""


def summarize_paper(model: genai.GenerativeModel, paper: dict, retries: int = 3) -> dict:
    prompt = _build_prompt(paper)
    for attempt in range(retries):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            # コードブロックで囲まれている場合を除去
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1])
            result = json.loads(text)
            return result
        except json.JSONDecodeError as e:
            print(f"  JSON解析エラー (attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                time.sleep(2)
        except Exception as e:
            print(f"  Gemini APIエラー (attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                time.sleep(5)

    # フォールバック
    return {
        "summary": paper.get("abstract", "要約を取得できませんでした。")[:200],
        "points": ["情報を取得できませんでした。", "", ""],
        "mermaid": 'flowchart LR\n    A["論文"] --> B["詳細は原著を参照"]',
        "importance": "medium",
    }


def enrich_papers(papers: list[dict]) -> list[dict]:
    model = _setup_gemini()
    enriched = []
    for i, paper in enumerate(papers):
        print(f"  Gemini 要約中 ({i+1}/{len(papers)}): {paper['title'][:60]}")
        ai = summarize_paper(model, paper)
        paper["ai_summary"] = ai.get("summary", "")
        paper["ai_points"] = ai.get("points", [])
        paper["ai_mermaid"] = ai.get("mermaid", "")
        paper["ai_importance"] = ai.get("importance", "medium")
        enriched.append(paper)
        if i < len(papers) - 1:
            time.sleep(2)
    return enriched


if __name__ == "__main__":
    sample = [{
        "title": "Mitochondrial transfer between cells can rescue aerobic respiration",
        "abstract": "We report that mitochondria can be transferred between mammalian cells. "
                    "This transfer rescued aerobic respiration in cells with non-functional mitochondria.",
        "authors": ["Islam MN", "Das SR", "Bhattacharya J"],
        "journal": "Nature Cell Biology",
        "year": 2012,
        "citation_count": 450,
        "doi": "10.1038/ncb2510",
        "open_access_url": "",
        "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/22246155/",
    }]
    results = enrich_papers(sample)
    print(json.dumps(results, ensure_ascii=False, indent=2))
