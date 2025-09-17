import requests
from bs4 import BeautifulSoup
import json
import time
import re

BASE = "https://www.dongyang.ac.kr"
LIST_URL = f"{BASE}/bbs/dmu/677/artclList.do"

headers = {
    "User-Agent": "Mozilla/5.0"
}

results = []

def clean_text(text: str) -> str:
    """본문 텍스트 정제 함수"""
    text = re.sub(r"\s+", " ", text)   # 연속 공백 → 하나로
    text = text.replace("\xa0", " ")   # 특수 공백 제거
    return text.strip()

for page in range(1, 11):  # 1 ~ 10 페이지
    params = {
        "page": page,
        "rows": 10,
        "srchBoardId": "677"
    }
    res = requests.get(LIST_URL, headers=headers, params=params)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")

    rows = soup.select("table.board-table tbody tr")

    for row in rows:
        title_tag = row.select_one("td.td-subject a")
        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        href = title_tag.get("href")
        if not href.startswith("http"):
            link = BASE + href
        else:
            link = href

        # 상세 페이지
        detail_res = requests.get(link, headers=headers)
        detail_res.encoding = "utf-8"
        detail_soup = BeautifulSoup(detail_res.text, "html.parser")

        # 본문 선택자 보완
        content = (detail_soup.select_one("div.view-con")
                or detail_soup.select_one("div.board-contents")
                or detail_soup.select_one("#contents"))

        content_text = clean_text(content.get_text(" ", strip=True)) if content else "[본문 없음]"

        results.append({
            "title": clean_text(title),
            "url": link,
            "content": content_text
        })

        time.sleep(0.5)

# JSON 저장
with open("result.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"총 {len(results)} 개 게시글을 저장했습니다.")
