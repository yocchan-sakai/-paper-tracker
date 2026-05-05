"""
全処理を順番に実行するメインスクリプト。
GitHub Actions から呼び出される。
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

import yaml
from fetch_papers import fetch_and_select, load_reported, _uid
from generate_site import build_site, save_results
from send_email import send_email
from summarize import enrich_papers

REPORTED_PATH = ROOT / "data" / "reported.json"
CONFIG_PATH = ROOT / "config.yml"


def update_reported(new_uids: list[str]) -> None:
    reported = list(load_reported())
    for uid in new_uids:
        if uid not in reported:
            reported.append(uid)
    REPORTED_PATH.write_text(json.dumps(reported, ensure_ascii=False, indent=2))
    print(f"reported.json 更新: {len(reported)} 件")


def main() -> None:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    keywords: list[str] = config.get("keywords", [])

    pages_url = os.environ.get("PAGES_URL", "")

    print("=" * 50)
    print("Step 1: 論文検索・Top3選出")
    print("=" * 50)
    papers, new_uids = fetch_and_select()

    if not papers:
        print("未報告の論文が見つかりませんでした。終了します。")
        sys.exit(0)

    print("\n" + "=" * 50)
    print("Step 2: Gemini で要約・図示生成")
    print("=" * 50)
    papers = enrich_papers(papers)

    print("\n" + "=" * 50)
    print("Step 3: データ保存・サイト生成")
    print("=" * 50)
    save_results(papers)
    build_site(papers, keywords)

    print("\n" + "=" * 50)
    print("Step 4: 報告済みリスト更新")
    print("=" * 50)
    update_reported(new_uids)

    print("\n" + "=" * 50)
    print("Step 5: メール送信")
    print("=" * 50)
    try:
        send_email(papers, pages_url)
    except Exception as e:
        print(f"メール送信エラー（継続）: {e}")

    print("\n✅ 完了！")
    for i, p in enumerate(papers, 1):
        print(f"  #{i} {p['title'][:70]}")


if __name__ == "__main__":
    main()
