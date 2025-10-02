from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import requests
import json
import time
import re

# ==========================
# Selenium 설정
# ==========================
options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": "https://www.dongyang.ac.kr/",
}

# ==========================
# 공통 함수
# ==========================
def clean_text_lines(soup):
    """본문을 줄 단위 string list로 정리"""
    if not soup:
        return ["본문 없음"]

    for tag in soup(["script", "style", "img", "button"]):
        tag.decompose()
    for a in soup.find_all("a"):
        a.replace_with(a.get_text(" ", strip=True))

    text = soup.get_text("\n", strip=True)
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


def crawl_static_page(url):
    """학과소개(원문 전체), 전공동아리 등 정적 페이지 기본 크롤링"""
    resp = requests.get(url, headers=COMMON_HEADERS, timeout=12)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    # 컨테이너가 페이지마다 달라서 후보 선택자 → 없으면 #contents
    candidates = [
        "#bContents .fr-view",
        "#contents .fr-view",
        "div._obj._objHtml._absolute",
        "#bContents .contents",
        "#contents .contents",
        "#bContents .conBody",
        "#contents .conBody",
    ]
    content = None
    for sel in candidates:
        node = soup.select_one(sel)
        if node:
            content = node
            break
    if content is None:
        content = soup.select_one("#bContents") or soup.select_one("#contents") or soup
    return clean_text_lines(content)

# ==========================
# NEW: 학과소개 — '졸업 후 진로' 전용 크롤러
# ==========================
def crawl_dept_intro_career(url):
    """
    '졸업 후 진로' 섹션만 추출.
    반환 예:
    {
      "취업분야": [...],
      "취업업체": [...],
      "취득가능자격증": [...]
    }
    """
    resp = requests.get(url, headers=COMMON_HEADERS, timeout=12)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 1) '졸업 후 진로' 헤더 div(underline H_4 등) 찾기
    header = soup.find(string=re.compile(r"\s*졸업\s*후\s*진로\s*"))
    if not header:
        raise RuntimeError("'졸업 후 진로' 헤더를 찾지 못했습니다.")
    header_div = header.find_parent("div")
    if not header_div:
        raise RuntimeError("'졸업 후 진로' 헤더의 래퍼 div를 찾지 못했습니다.")

    # 2) 헤더 이후의 형제 중 div.contents 3개(취업분야/취업업체/취득가능자격증)
    contents_blocks = []
    sib = header_div.next_sibling
    while sib and len(contents_blocks) < 3:
        if getattr(sib, "name", None) == "div" and "contents" in (sib.get("class") or []):
            contents_blocks.append(sib)
        sib = sib.next_sibling
    if not contents_blocks:
        raise RuntimeError("헤더 다음의 'div.contents' 블록을 찾지 못했습니다.")

    # 3) 각 블록에서 .con-tit(제목) + ul.boxwrap li(항목) 추출
    result = {}
    for block in contents_blocks:
        title_node = block.select_one(".con-tit")
        title = (title_node.get_text(" ", strip=True) if title_node else "").strip()
        items = [li.get_text(" ", strip=True) for li in block.select("ul.boxwrap li")]
        items = [x for x in items if x]
        if title:
            result[title] = items

    # 타이틀 표기가 다를 수 있으니 표준 키로 정렬(없으면 있는 것만 반환)
    normalized = {}
    if "취업분야" in result: normalized["취업분야"] = result["취업분야"]
    if "취업업체" in result: normalized["취업업체"] = result["취업업체"]
    if "취득가능자격증" in result: normalized["취득가능자격증"] = result["취득가능자격증"]
    # 예외적으로 제목이 다를 경우(예: 취업분야/진출분야 등)도 포함
    for k, v in result.items():
        if k not in normalized:
            normalized[k] = v
    return normalized


def parse_table_dict(table):
    """교육과정 테이블 → 챗봇 친화적인 딕셔너리 리스트 변환"""
    headers = [h.get_text(" ", strip=True) for h in table.find_all("th")]
    rows = []
    last_major = None

    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        if not cells:
            continue

        if cells[0] in ["전공필수", "전공선택", "교양필수", "교양선택"]:
            last_major = cells[0]
            if len(cells) < len(headers):
                cells += [""] * (len(headers) - len(cells))
            item = {headers[i]: cells[i] for i in range(len(headers))}
        else:
            cells = [last_major] + cells
            if len(cells) < len(headers):
                cells += [""] * (len(headers) - len(cells))
            item = {headers[i]: cells[i] for i in range(len(headers))}

        cleaned_item = {
            "이수구분": item.get("이수구분", ""),
            "교과목명": item.get("교과목명", ""),
            "학점": item.get("학점", ""),
            "개설학년·학기": item.get("개설학년·학기", "")
        }
        rows.append(cleaned_item)

    return rows


def crawl_curriculum(url):
    """Selenium으로 교육과정 페이지 크롤링"""
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    time.sleep(3)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    driver.quit()

    tables = soup.select(".contents table")
    all_data = []
    for t in tables:
        all_data.extend(parse_table_dict(t))
    return all_data


def crawl_professors(url):
    """교수소개 페이지 크롤링 (렌더링 필요)"""
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    time.sleep(3)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    driver.quit()

    professors = {}
    for prof in soup.select("li._prFlLi"):
        block = {}

        # 이름 + 직위
        name_tag = prof.select_one(".name strong")
        position_tag = prof.select_one(".name span")
        if not name_tag:
            continue
        name = name_tag.get_text(strip=True)
        position = position_tag.get_text(strip=True) if position_tag else ""

        # 기본 정보 (연구실, 연락처, 이메일)
        info_tags = prof.select(".info p")
        if info_tags:
            if len(info_tags) > 0: block["연구실"] = info_tags[0].get_text(strip=True)
            if len(info_tags) > 1: block["연락처"] = info_tags[1].get_text(strip=True)
            if len(info_tags) > 2: block["이메일"] = info_tags[2].get_text(strip=True)

        # 세부 정보 (전공분야, 담당과목, 보직 등)
        for dl in prof.select("dl"):
            dt = dl.select_one("dt")
            dd = dl.select_one("dd")
            if dt and dd:
                key = dt.get_text(strip=True)
                value = dd.get_text(strip=True)
                block[key] = value

        professors[f"{name}({position})"] = block

    return professors if professors else {"교수소개": "정보 없음"}


# ==========================
# 학과 전체 JSON 생성
# ==========================
def crawl_department(dept_name, urls):
    # 1) 학과소개(원문 전체)도 필요하면 활성화
    # intro_full = crawl_static_page(urls["학과소개"])

    # 2) 학과소개(졸업 후 진로만)
    intro_career = crawl_dept_intro_career(urls["학과소개"])

    result = {
        "학과명": dept_name,
        "sections": {
            # 원문 전체를 같이 저장하고 싶다면 아래 블록을 주석 해제
            # "학과소개(원문)": {
            #     "url": urls["학과소개"],
            #     "content": intro_full
            # },
            "학과소개(졸업 후 진로)": {
                "url": urls["학과소개"],
                "content": intro_career  # {"취업분야":[...], "취업업체":[...], "취득가능자격증":[...]}
            },
            "교육과정": {
                "전문학사": {
                    "url": urls["교육과정"]["전문학사"],
                    "content": crawl_curriculum(urls["교육과정"]["전문학사"])
                },
                "전문학사(P-TECH)": {
                    "url": urls["교육과정"]["전문학사(산업체위탁)"],
                    "content": crawl_curriculum(urls["교육과정"]["전문학사(산업체위탁)"])
                }
            },
            "교수소개": {
                "url": urls["교수소개"],
                "content": crawl_professors(urls["교수소개"])
            },
            "전공동아리": {
                "동아리1": {
                    "url": urls["전공동아리"]["동아리1"],
                    "content": crawl_static_page(urls["전공동아리"]["동아리1"])
                },
                "동아리2": {
                    "url": urls["전공동아리"]["동아리2"],
                    "content": crawl_static_page(urls["전공동아리"]["동아리2"])
                },
                "동아리3": {
                    "url": urls["전공동아리"]["동아리3"],
                    "content": crawl_static_page(urls["전공동아리"]["동아리3"])
                }
            }
        }
    }
    return result


# ==========================
# 실행 예시
# ==========================
if __name__ == "__main__":
    dept_name = "기계설계공학과"
    URLS = {
        "학과소개": "https://www.dongyang.ac.kr/dmu/4468/subview.do",
        "교육과정": {
            "전문학사": "https://www.dongyang.ac.kr/dmu/4471/subview.do",
            "전문학사(산업체위탁)": "https://www.dongyang.ac.kr/dmu/4471/subview.do?enc=Zm5jdDF8QEB8JTJGY3VycmklMkZkbXUlMkY0MCUyRmFydGNsTGlzdC5kbyUzRnNlbEdiJTNEJUVDJUEwJTg0JUVCJUFDJUI4JUVEJTk1JTk5JUVDJTgyJUFDJTI4JUVDJTgyJUIwJUVDJTk3JTg1JUVDJUIyJUI0JUVDJTlDJTg0JUVEJTgzJTgxJTI5JTI2c2VsWWVhciUzRCUyNg%3D%3D"
        },
        "교수소개": "https://www.dongyang.ac.kr/dmu/4472/subview.do",
        "전공동아리": {
            "동아리1": "https://www.dongyang.ac.kr/dmu/4476/subview.do",
            "동아리2": "https://www.dongyang.ac.kr/dmu/4477/subview.do",
            "동아리3": "https://www.dongyang.ac.kr/dmu/4478/subview.do"
        }
    }

    result = crawl_department(dept_name, URLS)

    with open(f"{dept_name}_전체.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ {dept_name}_전체.json 저장 완료")
