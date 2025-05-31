import os
from typing import Dict, Optional, Any, List
import datetime
import json

from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.exceptions import OutputParserException
from dotenv import load_dotenv

from project_memory import ProjectMemory
import config

load_dotenv()

os.environ["LANGCHAIN_TRACING_V2"] = "false"

class LLMService:
    def __init__(self, api_key,session_id:str,voice_handler=None, user_id="default_user"):
        self.voice_handler = voice_handler
        self.user_id = user_id
        self.session_id = session_id
        self.project_id = "default_project"

        self.llm = None
        self.rag_chain = None

        if not api_key:
            msg = "Gemini API key not provided. LLM Service will be offline."
            if self.voice_handler: self.voice_handler.speak(msg)
            else: print(msg)
            return

        try:
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-flash-latest",
                api_key=api_key,
                temperature=0.5
            )
            self.project_memory = ProjectMemory(faiss_path=config.FAISS_STORE_PATH, api_key=api_key)
            prompt = self._get_prompt_with_rag_retrieval()
            self.llm_call_chain = prompt | self.llm | StrOutputParser()

            msg = f"Jarvis LLM Service (with RAG via ProjectMemory for user '{self.user_id}') is online."
            if self.voice_handler: self.voice_handler.speak(msg)
            else: print(msg)

        except Exception as e:
            error_message = f"ERROR creating LLM service with ProjectMemory: {e}"
            print(error_message)
            if self.voice_handler: self.voice_handler.speak("Error initializing Jarvis's brain.")

    def _get_prompt_with_rag_retrieval(self):
        SYSTEM_PROMPT = """You are Jarvis, a proactive and friendly AI programming assistant.
        You are helping with a multi-file Python project.
        'Retrieved Chat History' below contains relevant past interactions (user requests and your previous JSON responses).
        If the user asks to recall or explain your previous response, analyze the relevant JSON objects from the 'Retrieved Chat History' to answer.
        Your primary goal is to respond to the 'Current User Request'.
        Be friendly, helpful, and direct. Do not use markdown for code. Always mention filenames.
        Your response MUST be a JSON object with keys "Suggested code" and "Guidance".
        "Suggested code" can be an empty string or "None" if no code is applicable.
        "Guidance" should explain your reasoning, next steps, or directly answer the user's query. If discussing code errors, try to reference line numbers if possible.
        """

        HUMAN_TEMPLATE = """
            Project Goal: {project_goal}
            File in focus: '{active_file_name}'
            Content of '{active_file_name}':
            --- BEGIN ACTIVE FILE CONTENT ---
            {active_file_code}
            --- END ACTIVE FILE CONTENT ---

            {context_files_string}

            --- RETRIEVED CHAT HISTORY (User & Your Past JSON Responses) ---
            {retrieved_chat_history}
            --- END RETRIEVED CHAT HISTORY ---

            Current User Request: {input}

            Please respond strictly in the following JSON format:
            {{
            "Suggested code": "<your code suggestion or 'None'>",
            "Guidance": "<your textual guidance and explanation, addressing any errors if applicable>"
            }}
        """
        return ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(SYSTEM_PROMPT),
            HumanMessagePromptTemplate.from_template(HUMAN_TEMPLATE)
        ])

    def clear_conversation_memory(self):
        msg = (f"Conceptual clear for user '{self.user_id}', session '{self.session_id}'. "
               f"FAISS-based ProjectMemory does not support simple per-session deletion. "
               f"New interactions will build on existing knowledge.")
        if self.voice_handler:
            self.voice_handler.speak(msg)
        else:
            print(msg)

    def get_code_guidance_with_project_context(
        self,
        user_command: str,
        active_file_path: str,
        active_file_code: str,
        project_context_files: Dict[str, str],
        user_project_goal:str,
        current_project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self.llm_call_chain or not self.project_memory:
            error_response = {"Error": "Jarvis LLM RAG chain or ProjectMemory is not initialized."}
            if self.voice_handler: self.voice_handler.speak(error_response["Error"])
            return error_response

        target_project_id = current_project_id if current_project_id else self.project_id

        active_file_name = os.path.basename(active_file_path) if active_file_path and active_file_path != "None" else "None"
        active_file_code_str = active_file_code if active_file_code and active_file_code.strip() else "This file is currently empty or not applicable."

        context_parts = []
        if project_context_files:
            context_parts.append("\n-- ADDITIONAL CONTEXT FILES --")
            for rel_file_path, file_content in project_context_files.items():
                name = os.path.basename(rel_file_path)
                if name == active_file_name: 
                    continue
                context_parts.append(f"\n-- Content of {rel_file_path} --")
                context_parts.append(file_content if file_content.strip() else "[This context file is empty]")
                context_parts.append(f"-- END {rel_file_path} --")
            context_parts.append("-- END ADDITIONAL CONTEXT FILES --")
        else:
            context_parts.append("No additional context files were provided for this request.")
        context_str = "\n".join(context_parts)

        retrieved_history_str = self.project_memory.load_chat_on_current_project(
            command_query=user_command,
            user_id=self.user_id,
            project_id=target_project_id,
            k=3
        )
        if "Error retrieving relevant history." in retrieved_history_str or "No relevant previous messages found" in retrieved_history_str:
             print(f"Note: {retrieved_history_str}")
             retrieved_history_str = "No relevant chat history found for this specific query and context."

        invoke_payload = {
            "project_goal": user_project_goal if user_project_goal else "Not specified.",
            "active_file_name": active_file_name,
            "active_file_code": active_file_code_str,
            "context_files_string": context_str,
            "retrieved_chat_history": retrieved_history_str,
            "input": user_command
        }

        raw_llm_output_str = ""
        try:
            print(f"\n--- Sending command to Jarvis (User: {self.user_id}, Session: {self.session_id}, Project: {target_project_id}) ---")
            print(f"User command: {user_command}")

            raw_llm_output_str = self.llm_call_chain.invoke(invoke_payload)
            print(f"--- Jarvis raw string response ---\n{raw_llm_output_str}")

            json_parser = JsonOutputParser()
            parsed_response = json_parser.parse(raw_llm_output_str)
            
            if not isinstance(parsed_response, dict) or "Guidance" not in parsed_response:
                print(f"[LLM WARNING] Parsed response was not a dict with 'Guidance' key: {parsed_response}")
                error_response = {"Error": "LLM response structure was unexpected after parsing.", "RawResponse": raw_llm_output_str}
                self.project_memory.add_response(user_command, self.user_id, self.session_id, target_project_id, message_type="human_error_query")
                self.project_memory.add_response(json.dumps(error_response), self.user_id, self.session_id, target_project_id, message_type="ai_error_response")
                return error_response

            self.project_memory.add_response(user_command, self.user_id, self.session_id, target_project_id, message_type="human")
            self.project_memory.add_response(raw_llm_output_str, self.user_id, self.session_id, target_project_id, message_type="ai")
            
            return parsed_response
        
        except OutputParserException as ope:
            error_msg = f"LLM output was not valid JSON: {ope}"
            print(error_msg)
            print(f"Raw LLM output that failed parsing: {raw_llm_output_str}")
            if self.voice_handler: self.voice_handler.speak("Jarvis's response was a bit garbled.")
            self.project_memory.add_response(user_command, self.user_id, self.session_id, target_project_id, message_type="human_parser_error_query")
            self.project_memory.add_response(raw_llm_output_str, self.user_id, self.session_id, target_project_id, message_type="ai_parser_error_response")
            return {"Error": error_msg, "RawResponse": raw_llm_output_str}
        except Exception as e:
            error_msg = f"Yikes! Something went wrong while talking to Jarvis: {e}"
            print(error_msg)
            if self.voice_handler: self.voice_handler.speak(error_msg)
            self.project_memory.add_response(user_command, self.user_id, self.session_id, target_project_id, message_type="human_exception_query")
            self.project_memory.add_response(json.dumps({"error": str(e)}), self.user_id, self.session_id, target_project_id, message_type="ai_exception_response")
            return {"Error": error_msg}

    def set_current_project(self, project_id: str):
        print(f"LLMService active project ID set to: {project_id}")
        self.project_id = project_id
        return project_id

    def get_last_ai_response_directly(self, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target_project_id = project_id if project_id else self.project_id
        filter_criteria = {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "project_id": target_project_id,
            "type": "ai"
        }
        history_str = self.project_memory._generic_load_chat_history(
            command_query="last AI response",
            filter_criteria=filter_criteria,
            k=1,
            sort_by_timestamp=True
        )

        if history_str and "Error" not in history_str and "No relevant previous messages found" not in history_str:
            try:
                parsed_response = json.loads(history_str)
                return parsed_response
            except json.JSONDecodeError:
                print(f"Error parsing last AI response from history string: {history_str}")
                return {"Error": "Could not parse last AI response from history.", "RawContent": history_str}
        return None

if __name__ == "__main__":
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("GOOGLE_API_KEY not found. Please set it in .env or environment variables.")
        exit()

    test_user_id = f"user_rag_test_{int(datetime.datetime.now().timestamp())}"
    
    jarvis = LLMService(api_key=api_key, user_id=test_user_id)
    jarvis.set_current_project("project_gamma_store")

    print(f"\n--- Test 1: Initial Interaction (User: {test_user_id}, Project: {jarvis.project_id}) ---")
    result1 = jarvis.get_code_guidance_with_project_context(
        user_command="Suggest a Python class for managing book data: title, author, isbn.",
        active_file_path="book_manager.py",
        active_file_code="",
        project_context_files={},
        user_project_goal="Develop a library book management system."
    )
    print("LLM Call Result 1:")
    print(json.dumps(result1, indent=2))
    if isinstance(result1, dict) and "Guidance" in result1:
        print(f"Guidance from Test 1: {result1['Guidance']}")

    print(f"\n--- Test 2: User asks LLM to recall (User: {test_user_id}, Project: {jarvis.project_id}) ---")
    result2 = jarvis.get_code_guidance_with_project_context(
        user_command="What did you suggest for the book class attributes?",
        active_file_path="book_manager.py",
        active_file_code="",
        project_context_files={},
        user_project_goal="Develop a library book management system."
    )
    print("LLM Call Result 2 (LLM recalling using RAG):")
    print(json.dumps(result2, indent=2))
    if isinstance(result2, dict) and "Guidance" in result2:
        print(f"Guidance from Test 2: {result2['Guidance']}")
        if "title" in result2.get("Guidance", "").lower() and "author" in result2.get("Guidance", "").lower():
             print("MEMORY TEST (LLM RAG Recall): SUCCESS - LLM seems to recall based on retrieved history.")
        else:
             print("MEMORY TEST (LLM RAG Recall): POTENTIAL ISSUE - LLM guidance might not strongly indicate recall.")

    print(f"\n--- Test 3: Application retrieves last AI response directly (User: {test_user_id}, Project: {jarvis.project_id}) ---")
    last_ai_response_from_app = jarvis.get_last_ai_response_directly()
    if last_ai_response_from_app:
        print("Application retrieved last AI response from ProjectMemory:")
        print(json.dumps(last_ai_response_from_app, indent=2))
        if isinstance(result1, dict) and isinstance(last_ai_response_from_app, dict) and \
           last_ai_response_from_app.get("Guidance") == result1.get("Guidance") and \
           last_ai_response_from_app.get("Suggested code") == result1.get("Suggested code"):
            print("DIRECT HISTORY RETRIEVAL TEST: SUCCESS - Retrieved last AI response matches original.")
        else:
            print("DIRECT HISTORY RETRIEVAL TEST: MISMATCH or ERROR - Retrieved response differs or error.")
    else:
        print("DIRECT HISTORY RETRIEVAL TEST: FAILED - Could not retrieve last AI response from history.")
    
    print(f"\n--- Test 4: Interaction with a different project (User: {test_user_id}) ---")
    jarvis.set_current_project("project_delta_store")
    result4 = jarvis.get_code_guidance_with_project_context(
        user_command="How do I set up a basic Flask route?",
        active_file_path="app.py",
        active_file_code="",
        project_context_files={},
        user_project_goal="Create a simple web API."
    )
    print("LLM Call Result 4 (New Project):")
    print(json.dumps(result4, indent=2))

    print(f"\n--- Test 5: Recall for Project Delta (User: {test_user_id}, Project: {jarvis.project_id}) ---")
    result5 = jarvis.get_code_guidance_with_project_context(
        user_command="What was that Flask route suggestion again?",
        active_file_path="app.py",
        active_file_code="",
        project_context_files={},
        user_project_goal="Create a simple web API."
    )
    print("LLM Call Result 5 (Recall Project Delta):")
    print(json.dumps(result5, indent=2))