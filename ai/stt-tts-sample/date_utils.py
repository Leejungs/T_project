# 상대일자 → 절대일 변환 등 후처리

from datetime import datetime, timedelta

def normalize_relative_dates_ko(text: str) -> str:
    today = datetime.now()

    rules = {
        "오늘": today,
        "내일": today + timedelta(days=1),
        "모레": today + timedelta(days=2),
        "이번주": today,  # 샘플: start of week로 바꾸고 싶으면 수정
        "다음주": today + timedelta(days=7),
        "이번달": today.replace(day=1),
        "다음달": (today.replace(day=28) + timedelta(days=4)).replace(day=1),
    }

    out = text
    for k, dt in rules.items():
        if k in out:
            out = out.replace(k, dt.strftime("%Y-%m-%d"))

    return out
