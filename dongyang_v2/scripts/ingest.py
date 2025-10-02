import os
import glob
import hashlib
from tqdm import tqdm
from typing import List

from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

# 프로젝트 루트 경로를 기준으로 app 폴더를 sys.path에 추가
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.config import settings

def run_ingestion():
    """PDF 문서를 로드, 분할하고 ChromaDB에 저장하는 전체 인제스트 파이프라인입니다."""
    print("--- 데이터 인제스트 파이프라인 시작 ---")

    # 1. 데이터 로드
    pdf_folder_path = "./pdf"
    pdf_files = glob.glob(os.path.join(pdf_folder_path, "*.pdf"))
    if not pdf_files:
        print(f"{pdf_folder_path}에서 PDF 파일을 찾을 수 없습니다. 파이프라인을 종료합니다.")
        return

    docs = []
    for pdf_file in tqdm(pdf_files, desc="PDF 파일 로드 중"):
        loader = UnstructuredPDFLoader(pdf_file, strategy="hi_res")
        docs.extend(loader.load())
    print(f"총 {len(docs)}개의 문서를 로드했습니다.")

    # 2. 문서 분할
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=150)
    split_docs = text_splitter.split_documents(docs)
    print(f"문서를 총 {len(split_docs)}개의 청크로 분할했습니다.")

    # 3. 임베딩 모델 로드
    print(f"임베딩 모델 '{settings.EMBEDDING_MODEL_NAME}' 로드 중...")
    embedding_function = HuggingFaceEmbeddings(
        model_name=settings.EMBEDDING_MODEL_NAME,
        model_kwargs={'device': 'cpu'}, # CPU 사용 명시
        encode_kwargs={'normalize_embeddings': True}
    )

    # 4. ChromaDB에 저장 (from_documents 사용)
    # 이 함수는 문서 분할, 임베딩, 저장을 한 번에 처리해주는 가장 안정적인 방법입니다.
    print("분할된 문서를 벡터로 변환하여 ChromaDB에 저장합니다...")
    vector_store = Chroma.from_documents(
        documents=split_docs,
        embedding=embedding_function,
        persist_directory=settings.VECTOR_DB_PATH,
        collection_name="school_info_collection"
    )

    print(f"--- 데이터 인제스트 완료! {len(split_docs)}개의 청크가 성공적으로 추가되었습니다. ---")

if __name__ == "__main__":
    run_ingestion()