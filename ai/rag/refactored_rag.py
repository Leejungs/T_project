import os
import re
import glob
import sys # Added for debugging sys.path
from typing import List, Dict, Optional

from langchain_core.documents import Document

from langchain_openai import ChatOpenAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import PyPDFLoader # Reverted import

from pymongo import MongoClient # Ensure this is present
from datetime import datetime

from .config import (
    CHROMA_DIR, COLLECTION_NAME, CHUNK_SIZE, CHUNK_OVERLAP,
    MONGO_URI, MONGO_COLL, MONGO_UPDATED_FIELD,
    PDF_GLOBS, DATA_DIR
)

# ... (other imports)

# --- Embeddings and LLM ---
embeddings = HuggingFaceEmbeddings(model_name="intfloat/multilingual-e5-small")
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

# --- Custom MongoDB Document Loader ---
class MongoDocumentLoader:
    def __init__(self, mongo_uri: str, collection_name: str, updated_field: str):
        self.client = MongoClient(mongo_uri)
        self.updated_field = updated_field
        self.target_collection_names = [c.strip() for c in collection_name.split(',') if c.strip()] if collection_name != "*" else []

    def load(self, query: Optional[Dict] = None) -> List[Document]:
        docs = []
        db_names = self.client.list_database_names()
        print(f"[DEBUG] MongoDocumentLoader: Found databases: {db_names}")
        for db_name in db_names:
            # Skip system databases
            if db_name in ["admin", "local", "config"]:
                print(f"[DEBUG] MongoDocumentLoader: Skipping system database: {db_name}")
                continue

            print(f"[DEBUG] MongoDocumentLoader: Processing database: {db_name}")
            db = self.client[db_name]
            collection_names_in_db = db.list_collection_names()
            print(f"[DEBUG] MongoDocumentLoader: Found collections in {db_name}: {collection_names_in_db}")

            collections_to_load = []
            if not self.target_collection_names: # If "*" was specified for MONGO_COLL
                collections_to_load = collection_names_in_db
            else:
                collections_to_load = [c for c in collection_names_in_db if c in self.target_collection_names]
            
            print(f"[DEBUG] MongoDocumentLoader: Collections to load in {db_name}: {collections_to_load}")

            for coll_name in collections_to_load:
                print(f"[DEBUG] MongoDocumentLoader: Loading from collection: {db_name}.{coll_name}")
                collection = db[coll_name]
                record_count = 0
                first_record_logged = False
                for record in collection.find(query or {}):
                    if not first_record_logged:
                        try:
                            with open("first_record.log", "w", encoding="utf-8") as f:
                                f.write("[DEBUG] First raw record from MongoDB:\n")
                                import json
                                f.write(json.dumps(record, indent=2, default=str))
                            print("[DEBUG] Saved the first raw record to first_record.log")
                        except Exception as e:
                            print(f"[DEBUG] Failed to log first record: {e}")
                        first_record_logged = True
                    
                    record_count += 1
                    content = self._flatten_mongo_record(record)
                    if content:
                        metadata = {
                            "source_type": "mongo",
                            "source_id": str(record.get("_id")),
                            "title": record.get("title", "No Title"),
                            "updated_at": self._coerce_ts(record.get(self.updated_field)),
                            "dataset": f"{db_name}.{coll_name}", # Include db_name in dataset
                            "uri": record.get("url") or record.get("link") or "",
                        }
                        docs.append(Document(page_content=content, metadata=metadata))
                print(f"[DEBUG] MongoDocumentLoader: Found {record_count} records in {db_name}.{coll_name}, {len(docs)} documents added from this DB.")
            print(f"[DEBUG] MongoDocumentLoader: Finished processing database: {db_name}")
        return docs

    def _flatten_mongo_record(self, record: Dict) -> str:
        parts = []
        TEXT_FIELD_CANDIDATES = (
            "title","subject","content","body","summary","text","desc","description",
            "content_html","html","markdown",
            "내용","본문","요약","설명","비고","세부내용","공지내용",
            "content_list","details",
        )

        ttl = record.get("title") or record.get("subject")
        if isinstance(ttl, str) and ttl.strip():
            parts.append(f"제목: {ttl.strip()}")

        if isinstance(record.get("content_list"), list) and record["content_list"]:
            parts.append(self._flatten_texts_recursive(record["content_list"]))
        if isinstance(record.get("details"), dict) and record["details"]:
            parts.append(self._flatten_texts_recursive(record["details"]))

        for k in TEXT_FIELD_CANDIDATES:
            if k in ("content_list", "details"):
                continue
            v = record.get(k)
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
            elif isinstance(v, (list, dict)):
                s = self._flatten_texts_recursive(v)
                if s:
                    parts.append(s)
        return (os.linesep * 2).join(parts).strip()

    def _flatten_texts_recursive(self, obj, max_len=30000) -> str:
        out = []
        def walk(x):
            if isinstance(x, str):
                t = x.strip()
                if t: out.append(t)
            elif isinstance(x, dict):
                for v in x.values(): walk(v)
            elif isinstance(x, (list, tuple)):
                for v in x: walk(v)
        walk(obj)
        return (os.linesep * 2).join(out)[:max_len]

    def _coerce_ts(self, v) -> Optional[int]:
        if isinstance(v, datetime): return int(v.timestamp())
        if isinstance(v, (int, float)):      return int(v)
        if isinstance(v, str):
            s = v.strip()
            if re.fullmatch(r"\d{10,13}", s):
                return int(s[:10])
            try:
                s2 = s.replace("Z", "").replace("T", " ")
                return int(datetime.fromisoformat(s2).timestamp())
            except Exception:
                return None
        return None

from pymongo import MongoClient
from datetime import datetime

from .config import (
    CHROMA_DIR, COLLECTION_NAME, CHUNK_SIZE, CHUNK_OVERLAP,
    MONGO_URI, MONGO_DB, MONGO_COLL, MONGO_UPDATED_FIELD,
    PDF_GLOBS, DATA_DIR
)

def _clean_metadata(metadata: Dict) -> Dict:
    print(f"[DEBUG] _clean_metadata: Original metadata: {metadata}")
    cleaned = {}
    for k, v in metadata.items():
        if k.startswith('_') and k != '_type': # Avoid internal ChromaDB keys, but keep _type
            continue
        if k == 'dataset' and isinstance(v, str) and '.' in v:
            # Extract db_name from dataset (e.g., 'db_name.collection_name')
            cleaned['db_name'] = v.split('.')[0]
            cleaned[k] = v # Keep original dataset as well
        elif isinstance(v, (str, int, float, bool)):
            cleaned[k] = v
        elif v is None:
            continue # Remove None values
        else:
            # Convert complex types to string representation
            cleaned[k] = str(v)
    print(f"[DEBUG] _clean_metadata: Cleaned metadata: {cleaned}")
    return cleaned

# --- Ingestion Function ---
def ingest_data(pdf_paths: Optional[List[str]] = None, mongo_query: Optional[Dict] = None):
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        import chromadb
        print(f"[DEBUG] sys.path: {sys.path}")
        documents = []

        # Automatically discover PDF files if not provided
        if not pdf_paths:
            _pdf_paths = []
            abs_data_dir = os.path.abspath(DATA_DIR)
            print(f"[DEBUG] Automatically discovering PDFs in {abs_data_dir} with globs {PDF_GLOBS}")
            for pattern in PDF_GLOBS:
                full_pattern = os.path.join(abs_data_dir, pattern)
                _pdf_paths.extend(glob.glob(full_pattern, recursive=True))
            pdf_paths = _pdf_paths
            print(f"[DEBUG] Discovered {len(pdf_paths)} PDF files: {pdf_paths}")

        mongo_loader = MongoDocumentLoader(MONGO_URI, MONGO_COLL, MONGO_UPDATED_FIELD)
        loaded_mongo_docs = mongo_loader.load(mongo_query)
        print(f"[DEBUG]     Loaded {len(loaded_mongo_docs)} documents from MongoDB sources.")
        documents.extend(loaded_mongo_docs)

        # Load PDF documents if paths are provided
        if pdf_paths:
            print(f"[DEBUG] Processing {len(pdf_paths)} PDF paths...")
            for p_path in pdf_paths:
                try:
                    loader = PyPDFLoader(p_path)
                    loaded_pdf_docs = loader.load()
                    print(f"[DEBUG]     Loaded {len(loaded_pdf_docs)} documents from PDF: {p_path}")
                    documents.extend(loaded_pdf_docs)
                except Exception as pdf_e:
                    print(f"[DEBUG]     Error loading PDF {p_path}: {pdf_e}")

        print(f"[DEBUG] Total documents before splitting: {len(documents)}") # Re-added in correct place

        # Split documents
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
        splits = text_splitter.split_documents(documents)
        print(f"[DEBUG] Value of splits after splitting: {len(splits)} splits.")
        print(f"[DEBUG] Number of splits: {len(splits)}")
        if splits:
            print(f"[DEBUG] First split content: {splits[0].page_content[:200]}")
            print(f"[DEBUG] First split metadata (before cleaning): {splits[0].metadata}\n")

            # Add new logging here
            import tiktoken
            encoding = tiktoken.get_encoding("cl100k_base") # Common encoding for GPT models

            print("[DEBUG] --- Sample Chunks Content and Token Counts (tiktoken) ---")
            for i, split in enumerate(splits[:5]): # Log first 5 splits
                content = split.page_content
                tokens = encoding.encode(content)
                print(f"[DEBUG] Split {i+1} (Chars: {len(content)}, Tokens: {len(tokens)}):")
                print(f"[DEBUG] Content (first 200 chars): {content[:200]}")
                print(f"[DEBUG] Metadata: {split.metadata}")
                print("-" * 20)
            print("[DEBUG] --- End Sample Chunks ---")

        cleaned_splits = []
        for doc in splits:
            doc.metadata = _clean_metadata(doc.metadata)
            cleaned_splits.append(doc)
        if cleaned_splits:
            print(f"[DEBUG] First split metadata (after cleaning): {cleaned_splits[0].metadata}\n")

        if not cleaned_splits: # Add this check
            print("[DEBUG] No cleaned splits to process.")
            print(f"Ingested 0 chunks into ChromaDB.") # Handle this case
            return

        # Manually prepare texts, metadatas, and ids for chromadb client
        texts = []
        metadatas = []
        ids = []
        for i, doc in enumerate(cleaned_splits):
            texts.append(doc.page_content)
            metadatas.append(doc.metadata)
            # Generate a unique ID for each chunk
            doc_id = f"chunk_{hash(doc.page_content + str(doc.metadata))}"
            ids.append(doc_id)

        if not texts:
            print("[DEBUG] No texts to add to ChromaDB.")
            print(f"Ingested 0 chunks into ChromaDB.") # Handle this case
            return

        # Manually generate embeddings
        embeddings_list = embeddings.embed_documents(texts)

        # Initialize raw chromadb client
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        collection = client.get_or_create_collection(name=COLLECTION_NAME)

        # Add data to chromadb collection
        collection.add(
            documents=texts,
            embeddings=embeddings_list,
            metadatas=metadatas,
            ids=ids
        )
        print(f"Ingested {len(texts)} chunks into ChromaDB.") # Changed to len(texts)
    except Exception as e: # Add except block here
        print(f"[DEBUG] Error in ingest_data: {e}")
        import traceback
        traceback.print_exc()
        raise # Re-raise the exception so FastAPI catches it





# --- QA Function ---


def ask_question(query: str, k: int = 3, filters: Optional[Dict[str, List[str]]] = None) -> Dict:


    import chromadb


    from langchain_chroma import Chroma


    from langchain.chains.combine_documents import create_stuff_documents_chain


    from langchain.chains import create_retrieval_chain


    from langchain_core.prompts import ChatPromptTemplate


    from langchain_core.documents import Document





    # Initialize the ChromaDB client


    client = chromadb.PersistentClient(path=CHROMA_DIR)





    # Get all collections


    collections = client.list_collections()


    if not collections:


        print("[DEBUG] No collections found in ChromaDB.")


        # Fallback to LLM without context


        try:


            prompt = ChatPromptTemplate.from_messages([


                ("system", "You are a helpful assistant. Answer the user's question based on the provided context."),


                ("user", "Question: {input}")


            ])


            question_answer_chain = create_stuff_documents_chain(llm, prompt)


            result = question_answer_chain.invoke({"input": query, "context": []})


            answer_text = result


        except Exception as e:


            print(f"[DEBUG] Error during fallback LLM invocation: {e}")


            answer_text = "답변을 생성할 수 없습니다."


        return {"answer": answer_text, "sources": []}





    # Keyword-based routing logic


    keyword_to_db = {


        "Academic_Information_db": ["휴학", "병결", "졸업", "성적"],


        "University_Introduction": ["시설", "번호", "센터"],


        "depatement_all_db": ["교수", "학과 소개", "자격증", "직장"],


    }





    target_db = None


    for db_name, keywords in keyword_to_db.items():


        if any(keyword in query for keyword in keywords):


            target_db = db_name


            break





    collections_to_query = []


    if target_db:


        for collection in collections:


            if collection.name.startswith(target_db):


                collections_to_query.append(collection)


        print(f"[DEBUG] Keyword found in query. Filtering to collections in {target_db}.")


    else:


        # If no specific keywords are found, search all collections


        collections_to_query = collections


        print("[DEBUG] No specific keywords found. Searching all collections.")





    if not collections_to_query:


        print("[DEBUG] No collections to query after filtering.")


        # Fallback to LLM without context


        try:


            prompt = ChatPromptTemplate.from_messages([


                ("system", "You are a helpful assistant. Answer the user's question based on the provided context."),


                ("user", "Question: {input}")


            ])


            question_answer_chain = create_stuff_documents_chain(llm, prompt)


            result = question_answer_chain.invoke({"input": query, "context": []})


            answer_text = result


        except Exception as e:


            print(f"[DEBUG] Error during fallback LLM invocation: {e}")


            answer_text = "답변을 생성할 수 없습니다."


        return {"answer": answer_text, "sources": []}





    all_source_documents = []


    


    for collection in collections_to_query:


        try:


            print(f"[DEBUG] Querying collection: {collection.name}")


            vectorstore = Chroma(


                client=client,


                collection_name=collection.name,


                embedding_function=embeddings,


            )





            # Create retriever for this collection


            search_kwargs = {"k": k}


            if filters:


                langchain_filters = {}


                for key, values in filters.items():


                    if isinstance(values, list) and len(values) == 1:


                        langchain_filters[key] = values[0]


                    else:


                        langchain_filters[key] = {"$in": values}


                search_kwargs["filter"] = langchain_filters


            


            retriever = vectorstore.as_retriever(search_kwargs=search_kwargs)


            


            # Retrieve documents from this collection


            source_documents = retriever.get_relevant_documents(query)


            


            if source_documents:


                print(f"[DEBUG] Retrieved {len(source_documents)} source documents from {collection.name}.")


                all_source_documents.extend(source_documents)





        except Exception as e:


            print(f"[DEBUG] Error querying collection {collection.name}: {e}")





    if not all_source_documents:


        print("[DEBUG] No source documents found across all collections.")


        # Fallback to LLM without context


        try:


            prompt = ChatPromptTemplate.from_messages([


                ("system", "You are a helpful assistant. Answer the user's question based on the provided context."),


                ("user", "Question: {input}")


            ])


            question_answer_chain = create_stuff_documents_chain(llm, prompt)


            result = question_answer_chain.invoke({"input": query, "context": []})


            answer_text = result


        except Exception as e:


            print(f"[DEBUG] Error during fallback LLM invocation: {e}")


            answer_text = "답변을 생성할 수 없습니다."


        return {"answer": answer_text, "sources": []}





    # Limit the number of documents and truncate their content


    MAX_DOCS = 5


    MAX_CHARS_PER_DOC = 1000





    if len(all_source_documents) > MAX_DOCS:


        # A more sophisticated re-ranking would be better here,


        # but for now, we'll just take the first MAX_DOCS.


        all_source_documents = all_source_documents[:MAX_DOCS]





    truncated_documents = []


    for doc in all_source_documents:


        truncated_content = doc.page_content[:MAX_CHARS_PER_DOC]


        truncated_doc = Document(page_content=truncated_content, metadata=doc.metadata)


        truncated_documents.append(truncated_doc)





    # Use the truncated documents to generate an answer


    prompt = ChatPromptTemplate.from_messages([


        ("system", "You are a helpful assistant. Answer the user's question based on the provided context."),


        ("user", "Context:\n{context}\n\nQuestion: {input}")


    ])


    question_answer_chain = create_stuff_documents_chain(llm, prompt)


    


    result = question_answer_chain.invoke({"input": query, "context": truncated_documents})


    answer_text = result





    # Format output


    sources = []


    for doc in truncated_documents: # Use truncated_documents for the sources as well


        meta = doc.metadata


        sources.append({


            "id": meta.get("source_id"),


            "page": meta.get("page"),


            "title": meta.get("title"),


            "dataset": meta.get("dataset"),


            "uri": meta.get("uri"),


            "score": None,


            "source_type": meta.get("source_type"),


            "text": doc.page_content


        })





    return {"answer": answer_text, "sources": sources}

