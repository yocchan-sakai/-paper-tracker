"""
Gmail SMTP で Top3 論文をメール送信する。
"""

import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _build_html_email(papers: list[dict], pages_url: str) -> str:
    today = date.today().strftime("%Y年%m月%d日")
    cards = ""
    for i, p in enumerate(papers, 1):
        title = p.get("title", "")
        journal = p.get("journal", "")
        year = p.get("year", "")
        citations = p.get("citation_count", 0)
        summary = p.get("ai_summary", "")
        points = p.get("ai_points", [])
        oa_url = p.get("open_access_url", "")
        pubmed_url = p.get("pubmed_url", "")
        semantic_url = p.get("semantic_url", "")
        is_trending = p.get("is_trending", False)

        point_html = "".join(
            f'<li style="margin-bottom:6px;">[{j}] {pt}</li>'
            for j, pt in enumerate(points[:3], 1) if pt
        )

        links = []
        if oa_url:
            links.append(f'<a href="{oa_url}" style="color:#4f46e5;font-weight:bold;">PDF全文を読む</a>')
        if pubmed_url:
            links.append(f'<a href="{pubmed_url}" style="color:#4f46e5;">PubMed</a>')
        if semantic_url:
            links.append(f'<a href="{semantic_url}" style="color:#4f46e5;">Semantic Scholar</a>')
        link_html = " &nbsp;|&nbsp; ".join(links)

        trending_tag = '<span style="background:#10b981;color:#fff;font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px;margin-left:8px;">Trending</span>' if is_trending else ""
        cards += f"""
<div style="background:#fff;border:1px solid {'#d1fae5' if is_trending else '#e5e7eb'};border-radius:12px;
            padding:20px;margin-bottom:20px;">
  <p style="color:#818cf8;font-size:24px;font-weight:900;margin:0 0 4px;">#{i}{trending_tag}</p>
  <h2 style="font-size:16px;font-weight:700;color:#111827;margin:0 0 6px;
             line-height:1.4;">{title}</h2>
  <p style="font-size:13px;color:#6b7280;margin:0 0 12px;">
    {journal} ({year}) | 引用 {citations}
  </p>
  <p style="font-size:14px;color:#374151;margin:0 0 12px;
            line-height:1.7;">{summary}</p>
  <ul style="font-size:14px;color:#374151;padding-left:0;
             list-style:none;margin:0 0 14px;">{point_html}</ul>
  <p style="margin:0;">{link_html}</p>
</div>"""

    web_link = f'<p style="text-align:center;margin-top:24px;"><a href="{pages_url}" style="color:#4f46e5;">Web で詳しく見る（図解あり）→</a></p>' if pages_url else ""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:-apple-system,'Hiragino Sans',sans-serif;background:#f9fafb;
             padding:20px;margin:0;">
  <div style="max-width:600px;margin:0 auto;">
    <div style="background:#4f46e5;border-radius:12px;padding:20px 24px;
                margin-bottom:24px;text-align:center;">
      <h1 style="color:#fff;font-size:20px;margin:0;">Paper Tracker</h1>
      <p style="color:#c7d2fe;font-size:14px;margin:6px 0 0;">
        {today} の Top {len(papers)} 論文
      </p>
    </div>
    {cards}
    {web_link}
    <p style="text-align:center;font-size:12px;color:#9ca3af;margin-top:32px;">
      このメールは Paper Tracker により自動送信されました。
    </p>
  </div>
</body>
</html>"""


def _build_text_email(papers: list[dict]) -> str:
    today = date.today().strftime("%Y年%m月%d日")
    lines = [f"Paper Tracker - {today} の Top {len(papers)} 論文\n", "=" * 50]
    for i, p in enumerate(papers, 1):
        lines.append(f"\n#{i} {p.get('title', '')}")
        lines.append(f"   {p.get('journal','')} ({p.get('year','')}) | 引用 {p.get('citation_count',0)}")
        if p.get("ai_summary"):
            lines.append(f"\n   {p['ai_summary']}")
        for j, pt in enumerate(p.get("ai_points", [])[:3], 1):
            if pt:
                lines.append(f"   [{j}] {pt}")
        url = p.get("open_access_url") or p.get("pubmed_url") or p.get("semantic_url") or ""
        if url:
            lines.append(f"   → {url}")
        lines.append("")
    return "\n".join(lines)


def send_email(papers: list[dict], pages_url: str = "") -> None:
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    notify_email = os.environ.get("NOTIFY_EMAIL")

    if not all([gmail_address, gmail_password, notify_email]):
        print("メール設定が不完全です（GMAIL_ADDRESS / GMAIL_APP_PASSWORD / NOTIFY_EMAIL）")
        return

    today = date.today().strftime("%Y年%m月%d日")
    subject = f"[Paper Tracker] {today} の Top {len(papers)} 論文"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = notify_email

    msg.attach(MIMEText(_build_text_email(papers), "plain", "utf-8"))
    msg.attach(MIMEText(_build_html_email(papers, pages_url), "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, gmail_password)
        server.sendmail(gmail_address, notify_email, msg.as_string())

    print(f"メール送信完了: {notify_email}")


if __name__ == "__main__":
    sample = [{
        "title": "Test Paper",
        "journal": "Nature",
        "year": 2024,
        "citation_count": 10,
        "ai_summary": "テスト要約です。",
        "ai_points": ["ポイント1", "ポイント2", "ポイント3"],
        "open_access_url": "",
        "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/",
        "semantic_url": "",
    }]
    send_email(sample)
