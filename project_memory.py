import os
import json
import shutil
import datetime
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import InMemoryVectorStore
import config

load_dotenv()

class ProjectMemory:
    def __init__(self, api_key: Optional[str] = None):
        if api_key is None:
            api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("Google API Key not found.")
        self.embedding_model = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=api_key)
        self.persistence_path = os.path.join(config.FAISS_STORE_PATH, "memory_store.jsonl")
        self.store = InMemoryVectorStore(embedding=self.embedding_model)
        self._load_from_persistence()

    def _load_from_persistence(self):
        if not os.path.exists(self.persistence_path):
            return
        documents = []
        with open(self.persistence_path, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line.strip())
                documents.append(Document(page_content=data["page_content"], metadata=data["metadata"]))
        if documents:
            self.store.add_documents(documents)

    def _save_to_persistence(self):
        docs = self.store.similarity_search("", k=9999)
        with open(self.persistence_path, "w", encoding="utf-8") as f:
            for doc in docs:
                json.dump({"page_content": doc.page_content, "metadata": doc.metadata}, f)
                f.write("\n")

    def add_response(self, response_content: str, user_id: str, session_id: str, project_id: str, message_type: str = "ai"):
        doc = Document(
            page_content=response_content,
            metadata={
                "user_id": user_id,
                "session_id": session_id,
                "project_id": project_id,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "type": message_type
            }
        )
        self.store.add_documents([doc])
        self._save_to_persistence()

    def _generic_load_chat_history(self, query: str, filter_by: Dict[str, Any], k: int = 5) -> str:
        results = self.store.similarity_search_with_score(query, k=k * 2)
        filtered_docs = [doc for doc, _ in results if all(doc.metadata.get(k) == v for k, v in filter_by.items())]
        filtered_docs.sort(key=lambda d: d.metadata.get("timestamp", ""))
        if not filtered_docs:
            return "No relevant history found."
        return "\n---\n".join([
            f"PAST {doc.metadata.get('type', 'unknown').upper()} MESSAGE:\n{doc.page_content}"
            for doc in filtered_docs[-k:]
        ])

    def load_chat_on_current_project(self, query: str, user_id: str, project_id: str, k: int = 5) -> str:
        return self._generic_load_chat_history(query, {"user_id": user_id, "project_id": project_id}, k)

    def load_chat_for_user_session(self, query: str, user_id: str, session_id: str, k: int = 5) -> str:
        return self._generic_load_chat_history(query, {"user_id": user_id, "session_id": session_id}, k)

    def load_chat_on_user_date(self, query: str, user_id: str, time: str, k: int = 5) -> str:
        return self._generic_load_chat_history(query, {"user_id": user_id, "timestamp": time}, k)


if __name__ == "__main__":
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        exit()
    test_dir = os.path.join(os.path.dirname(__file__), "test_memory_persistence")
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    original_path = config.FAISS_STORE_PATH
    config.FAISS_STORE_PATH = test_dir

    memory = ProjectMemory(api_key)
    memory.add_response("Hello! How can I assist?", "user1", "sess1", "proj1", "ai")
    memory.add_response("I need help with deployment.", "user1", "sess1", "proj1", "human")

    memory = ProjectMemory(api_key)
    history = memory.load_chat_on_current_project("deployment", "user1", "proj1")
    print(history)

    shutil.rmtree(test_dir)
    config.FAISS_STORE_PATH = original_path
    print("Test completed successfully.")