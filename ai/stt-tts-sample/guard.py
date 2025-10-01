# 간단 가드레일(욕설/PII 감지)

import re

BAD_WORDS = ["씨발", "좆", "개새", "fuck", "shit"]
PII_PATTERNS = [
    r"\b\d{3}-\d{2}-\d{5}\b",   # 학번/주민 유사 패턴 예시(진짜 사용 전엔 정확 규칙 설계)
    r"\b010-\d{4}-\d{4}\b",     # 휴대폰 형식
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
]

def violates_policy(text: str) -> bool:
    if any(b in text for b in BAD_WORDS):
        return True
    for pat in PII_PATTERNS:
        if re.search(pat, text):
            return True
    return False
