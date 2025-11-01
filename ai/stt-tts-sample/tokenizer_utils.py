from tiktoken import encoding_for_model

enc = encoding_for_model("gpt-4o-mini")  # 또는 "gpt-4", "text-embedding-3-large"
total_tokens = 0

for chunk in texts:
    total_tokens += len(enc.encode(chunk.page_content))

print(f"총 청크 수: {len(texts)}")
print(f"총 토큰 수: {total_tokens}")
