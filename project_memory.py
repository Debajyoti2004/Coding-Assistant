import os
import uuid
import datetime
from typing import List, Dict, Any, Callable, Optional

from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv
import config
load_dotenv()


class ProjectMemory:
    def __init__(self, faiss_path: str = config.FAISS_STORE_PATH, api_key: Optional[str] = None):
        if api_key is None:
            api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("Google API Key not found. Please set it in .env or pass it as an argument.")

        self.embedding_model = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=api_key)
        
        self.faiss_path = faiss_path
        self.store: Optional[FAISS] = None

        if os.path.exists(os.path.join(faiss_path, "index.faiss")):
            try:
                self.store = FAISS.load_local(
                    folder_path=faiss_path,
                    embeddings=self.embedding_model,
                    allow_dangerous_deserialization=True
                )
                print(f"FAISS vector store loaded from path: {faiss_path}")
            except Exception as e:
                print(f"Error loading existing FAISS store from {faiss_path}: {e}. Will attempt to create a new one.")
                self._initialize_new_store()
        else:
            self._initialize_new_store()

    def _initialize_new_store(self):
        os.makedirs(self.faiss_path, exist_ok=True)
        placeholder_document = Document(
            page_content="Initial placeholder document for FAISS index.",
            metadata={
                "user_id": "system_placeholder",
                "project_id": "system_placeholder",
                "session_id": "system_placeholder",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "type": "system"
            }
        )
        try:
            self.store = FAISS.from_documents(
                documents=[placeholder_document],
                embedding=self.embedding_model
            )
            self.store.save_local(folder_path=self.faiss_path)
            print(f"New FAISS index created with a placeholder and saved to {self.faiss_path}")
        except Exception as e:
            print(f"FATAL: Could not initialize new FAISS store at {self.faiss_path}: {e}")
            raise

    def add_response(self,
                     response_content: str,
                     user_id: str,
                     session_id: str,
                     project_id: str,
                     message_type: str = "ai"):
        if self.store is None:
            print("Error: FAISS store is not initialized. Cannot add response.")
            return

        document = Document(
            page_content=response_content,
            metadata={
                "user_id": str(user_id),
                "project_id": str(project_id),
                "session_id": str(session_id),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "type": message_type
            }
        )
        try:
            self.store.add_documents(documents=[document])
            self.store.save_local(folder_path=self.faiss_path)
            print(f"Response added to FAISS. Metadata: user_id={user_id}, project_id={project_id}, session_id={session_id}")
        except Exception as e:
            print(f"Error adding document to FAISS or saving: {e}")

    def _generic_load_chat_history(self,
                                   command_query: str,
                                   filter_criteria: Dict[str, Any],
                                   k: int = 8,
                                   sort_by_timestamp: bool = True) -> str:
        if self.store is None:
            print("Error: FAISS store is not initialized. Cannot load history.")
            return "Error: Memory store not available."

        try:
            results_with_scores = self.store.similarity_search_with_score(query=command_query, k=k*2)
            results = [doc for doc, score in results_with_scores]
            
            def _filter_doc(doc: Document) -> bool:
                for key, value in filter_criteria.items():
                    if doc.metadata.get(key) != value:
                        return False
                return True

            filtered_docs = [doc for doc in results if _filter_doc(doc)]

            if sort_by_timestamp:
                filtered_docs.sort(key=lambda doc: doc.metadata.get("timestamp", ""), reverse=True)
            
            final_docs = filtered_docs[:k]

            if not final_docs:
                return "No relevant previous messages found matching your criteria."
                
            return "\n---\n".join([doc.metadata.get("type")+":\t"+doc.page_content+"\tDate:"+doc.metadata.get("timestamp") for doc in final_docs])
        except Exception as e:
            print(f"Error loading chat history from FAISS: {e}")
            return "Error retrieving relevant history."

    def load_chat_on_current_project(self,
                                               command_query: str,
                                               user_id: str,
                                               project_id: str,
                                               k: int = 5) -> str:
        filter_criteria = {
            "user_id": str(user_id),
            "project_id": str(project_id)
        }
        print(f"Loading history for project: {project_id}, user: {user_id}")
        return self._generic_load_chat_history(command_query, filter_criteria, k=k)

    def load_chat_for_user_session(self,
                                           command_query: str,
                                           user_id: str,
                                           session_id: str,
                                           k: int = 5) -> str:
        filter_criteria = {
            "user_id": str(user_id),
            "session_id": str(session_id)
        }
        print(f"Loading history for user: {user_id}, session: {session_id} (all projects)")
        return self._generic_load_chat_history(command_query, filter_criteria, k=k)
    
    def load_chat_on_user_date(self,
                                command_query: str,
                                user_id: str,
                                time: str,
                                k: int = 5) -> str:
        filter_criteria = {
            "user_id": str(user_id),
            "timestamp": str(time)
        }
        print(f"Loading history for user: {user_id}, timestamp:{time} (all projects)")
        return self._generic_load_chat_history(command_query, filter_criteria, k=k)
    

if __name__ == "__main__":
    if not os.getenv("GOOGLE_API_KEY"):
        print("Please set your GOOGLE_API_KEY in a .env file.")
        exit()

    test_faiss_path = os.path.join(config.FAISS_STORE_PATH, f"test_run_{uuid.uuid4().hex[:8]}")
    if os.path.exists(test_faiss_path):
        import shutil
        shutil.rmtree(test_faiss_path)

    print(f"Using FAISS path for test: {test_faiss_path}")
    memory = ProjectMemory(faiss_path=test_faiss_path)

    user1 = str(uuid.uuid4())
    session1 = "session_abc"
    project1 = "project_alpha"
    project2 = "project_beta"

    memory.add_response("Response 1 for Alpha: planning phase.", user1, session1, project1, message_type="ai")
    memory.add_response("Human asking about Alpha: What's next?", user1, session1, project1, message_type="human")
    memory.add_response("Response 2 for Alpha: development.", user1, session1, project1, message_type="ai")
    
    memory.add_response("Response 1 for Beta: kickoff meeting.", user1, session1, project2, message_type="ai")
    memory.add_response("Human question for Beta: Any blockers?", user1, session1, project2, message_type="human")

    print("\n--- Testing load_previous_chat_on_current_project (Alpha) ---")
    chat_alpha = memory.load_previous_chat_on_current_project(
        command_query="current status of Alpha",
        user_id=user1,
        session_id=session1,
        project_id=project1
    )
    print(f"Chat history for Project Alpha:\n{chat_alpha}")

    print("\n--- Testing load_previous_chat_on_current_project (Beta) ---")
    chat_beta = memory.load_previous_chat_on_current_project(
        command_query="details about Beta project",
        user_id=user1,
        session_id=session1,
        project_id=project2
    )
    print(f"Chat history for Project Beta:\n{chat_beta}")

    print("\n--- Testing load_previous_chat_for_user_session (All projects for user1/session1) ---")
    chat_user_session = memory.load_previous_chat_for_user_session(
        command_query="summary of my activities",
        user_id=user1,
        session_id=session1
    )
    print(f"Chat history for User {user1}, Session {session1}:\n{chat_user_session}")
    
    print("\n--- Testing retrieval with no matching project ---")
    chat_non_existent = memory.load_previous_chat_on_current_project(
        command_query="status of Gamma",
        user_id=user1,
        session_id=session1,
        project_id="project_gamma"
    )
    print(f"Chat history for Project Gamma:\n{chat_non_existent}")