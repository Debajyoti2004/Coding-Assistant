import os
from typing import Dict, Optional, Any, List
import datetime
import json
import shutil

from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.exceptions import OutputParserException
from langchain.memory.buffer import ConversationBufferMemory
from langchain_core.messages import HumanMessage, AIMessage
from dotenv import load_dotenv

from project_memory import ProjectMemory
import config

load_dotenv()

os.environ["LANGCHAIN_TRACING_V2"] = "false"

class LLMService:
    def __init__(self, api_key, session_id:str, voice_handler=None, user_id="default_user"):
        self.voice_handler = voice_handler
        self.user_id = user_id
        self.session_id = session_id
        self.project_id = "default_project"
        self.llm = None
        self.llm_call_chain = None

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
            self.project_memory = ProjectMemory(api_key=api_key)
            self.buffer_memory = ConversationBufferMemory(memory_key="current_conversation_history", return_messages=False)
            prompt = self._get_prompt_with_rag_retrieval()
            self.llm_call_chain = prompt | self.llm | StrOutputParser()
            msg = f"Jarvis LLM Service is online."
            if self.voice_handler: self.voice_handler.speak(msg)
            else: print(msg)
        except Exception as e:
            error_message = f"ERROR creating LLM service: {e}"
            print(error_message)
            if self.voice_handler: self.voice_handler.speak("Error initializing Jarvis's brain.")

    def _get_prompt_with_rag_retrieval(self):
        SYSTEM_PROMPT = """You are Jarvis, a proactive and friendly AI programming assistant.
        'Retrieved Chat History' contains relevant past interactions from long-term memory.
        'Current Conversation' contains the most recent back-and-forth messages in this session.
        Use both to understand the full context. Your primary goal is to respond to the 'Current User Request'.
        Be friendly, helpful, and direct. Do not use markdown for code.
        Your response MUST be a JSON object with keys "Suggested code" and "Guidance".
        """
        HUMAN_TEMPLATE = """
            Project Goal: {project_goal}
            File in focus: '{active_file_name}'
            Content of '{active_file_name}':
            --- BEGIN ACTIVE FILE CONTENT ---
            {active_file_code}
            --- END ACTIVE FILE CONTENT ---
            {context_files_string}
            --- RETRIEVED CHAT HISTORY (Long-Term Memory) ---
            {retrieved_chat_history}
            --- END RETRIEVED CHAT HISTORY ---
            --- CURRENT CONVERSATION (Short-Term Memory) ---
            {current_conversation_history}
            --- END CURRENT CONVERSATION ---
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
        self.buffer_memory.clear()
        msg = "Current conversation history has been cleared."
        if self.voice_handler:
            self.voice_handler.speak(msg)
        else:
            print(msg)
            
    def save_conversation_to_long_term_memory(self):
        messages = self.buffer_memory.chat_memory.messages
        if not messages:
            msg = "Nothing in the current conversation to save."
            if self.voice_handler: self.voice_handler.speak(msg)
            else: print(msg)
            return

        print(f"Saving {len(messages)} messages to long-term memory for project '{self.project_id}'...")
        for message in messages:
            if isinstance(message, HumanMessage):
                self.project_memory.add_response(message.content, self.user_id, self.session_id, self.project_id, message_type="human")
            elif isinstance(message, AIMessage):
                self.project_memory.add_response(message.content, self.user_id, self.session_id, self.project_id, message_type="ai")
        
        self.buffer_memory.clear()
        
        msg = "Current conversation has been saved to long-term memory. Ready for the next topic."
        if self.voice_handler: self.voice_handler.speak(msg)
        else: print(msg)

    def get_code_guidance_with_project_context(
        self,
        user_command: str,
        active_file_path: str,
        active_file_code: str,
        project_context_files: Dict[str, str],
        user_project_goal:str,
        current_project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self.llm_call_chain:
            return {"Error": "Jarvis LLM RAG chain is not initialized."}

        target_project_id = current_project_id if current_project_id else self.project_id
        active_file_name = os.path.basename(active_file_path) if active_file_path else "None"
        active_file_code_str = active_file_code or "This file is currently empty."
        context_str = "\n".join([f"-- Content of {path} --\n{content}" if os.path.basename(path)!=active_file_name else "" for path, content in project_context_files.items()])

        retrieved_history_str = self.project_memory.load_chat_on_current_project(
            query=user_command,
            user_id=self.user_id,
            project_id=target_project_id,
            k=3
        )
        current_conversation_str = self.buffer_memory.load_memory_variables({})['current_conversation_history']

        invoke_payload = {
            "project_goal": user_project_goal or "Not specified.",
            "active_file_name": active_file_name,
            "active_file_code": active_file_code_str,
            "context_files_string": context_str,
            "retrieved_chat_history": retrieved_history_str,
            "current_conversation_history": current_conversation_str,
            "input": user_command
        }

        raw_llm_output_str = ""
        try:
            raw_llm_output_str = self.llm_call_chain.invoke(invoke_payload)

            json_parser = JsonOutputParser()
            parsed_response = json_parser.parse(raw_llm_output_str)

            self.buffer_memory.save_context({"input": user_command}, {"output": raw_llm_output_str})
            
            return parsed_response
        
        except OutputParserException as ope:
            error_msg = f"LLM output was not valid JSON: {ope}"
            if self.voice_handler: self.voice_handler.speak("Jarvis's response was a bit garbled.")
            self.buffer_memory.save_context({"input": user_command}, {"output": f"LLM_ERROR: {raw_llm_output_str}"})
            return {"Error": error_msg, "RawResponse": raw_llm_output_str}
        except Exception as e:
            error_msg = f"An error occurred while talking to Jarvis: {e}"
            if self.voice_handler: self.voice_handler.speak(error_msg)
            return {"Error": error_msg}

    def set_current_project(self, project_id: str):
        self.project_id = project_id
        self.buffer_memory.clear()
        print(f"LLMService active project ID set to: {project_id}. Conversation buffer cleared.")
        return project_id

    def get_last_ai_response_directly(self, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        target_project_id = project_id if project_id else self.project_id
        
        last_doc_str = self.project_memory._generic_load_chat_history(
            command_query="last ai response",
            filter_criteria={"user_id": self.user_id, "project_id": target_project_id, "type": "ai"},
            k=1
        )

        if last_doc_str and "Error" not in last_doc_str and "No relevant" not in last_doc_str:
            try:
                json_part = last_doc_str.split("PAST AI MESSAGE:\n", 1)[1]
                return json.loads(json_part)
            except (json.JSONDecodeError, IndexError):
                return {"Error": "Could not parse last AI response from history.", "RawContent": last_doc_str}
        return None


if __name__ == "__main__":
    class MockVoiceHandler:
        def speak(self, text: str, tag: str = 'assistant'):
            print(f"[MOCK ASSISTANT SPEAKS]: {text}")

    def run_test():
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("FATAL: GOOGLE_API_KEY not found in .env file. Test cannot run.")
            return

        test_dir = os.path.join(os.path.dirname(__file__), "test_llm_run")
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
        os.makedirs(test_dir)
        
        original_path = config.FAISS_STORE_PATH
        config.FAISS_STORE_PATH = test_dir
        
        print("-" * 50)
        print(f"Starting test in temporary directory: {test_dir}")
        print("-" * 50)

        try:
            mock_voice = MockVoiceHandler()
            session_id = f"test_session_{int(datetime.datetime.now().timestamp())}"
            jarvis = LLMService(api_key=api_key, session_id=session_id, voice_handler=mock_voice)
            jarvis.set_current_project("project_test_alpha")

            print("\n--- TEST 1: Initial Question & Short-Term Memory Follow-up ---")
            
            print("\n[USER]: Suggest a simple Python function to greet a user.")
            result1 = jarvis.get_code_guidance_with_project_context(
                user_command="Suggest a simple Python function to greet a user.",
                active_file_path="main.py", active_file_code="",
                project_context_files={}, user_project_goal="Create a simple CLI tool."
            )
            print(f"LLM Response 1:\n{json.dumps(result1, indent=2)}\n")

            print("\n[USER]: Now change it to say goodbye instead.")
            result2 = jarvis.get_code_guidance_with_project_context(
                user_command="Now change it to say goodbye instead.",
                active_file_path="main.py", active_file_code=result1.get("Suggested code", ""),
                project_context_files={}, user_project_goal="Create a simple CLI tool."
            )
            print(f"LLM Response 2 (testing buffer):\n{json.dumps(result2, indent=2)}\n")
            if "goodbye" in result2.get("Guidance", "").lower():
                print("✅ SHORT-TERM MEMORY TEST: SUCCESS! The assistant remembered the previous context.")
            else:
                print("❌ SHORT-TERM MEMORY TEST: FAILED! The assistant did not seem to remember.")

            print("\n--- TEST 2: Clearing Conversation & Re-asking Follow-up ---")
            jarvis.clear_conversation_memory()

            print("\n[USER]: Now change it to say goodbye instead. (Asked after clearing memory)")
            result3 = jarvis.get_code_guidance_with_project_context(
                user_command="Now change it to say goodbye instead.",
                active_file_path="main.py", active_file_code="",
                project_context_files={}, user_project_goal="Create a simple CLI tool."
            )
            print(f"LLM Response 3 (after clearing):\n{json.dumps(result3, indent=2)}\n")
            if "what function" in result3.get("Guidance", "").lower() or "which function" in result3.get("Guidance", "").lower():
                print("✅ CLEAR MEMORY TEST: SUCCESS! The assistant was correctly confused.")
            else:
                print("❌ CLEAR MEMORY TEST: FAILED! The assistant may not have cleared its short-term buffer.")

            print("\n--- TEST 3: Saving a Conversation to Long-Term Memory ---")
            jarvis.clear_conversation_memory()
            print("\n[USER]: Create a class to represent a Car with make and model attributes.")
            car_result = jarvis.get_code_guidance_with_project_context(
                user_command="Create a class to represent a Car with make and model attributes.",
                active_file_path="models.py", active_file_code="",
                project_context_files={}, user_project_goal="Model real-world objects."
            )
            print(f"LLM Response (Car Class):\n{json.dumps(car_result, indent=2)}\n")

            jarvis.save_conversation_to_long_term_memory()

            print("\n--- TEST 4: Verifying Long-Term Memory (RAG) After 'Restart' ---")
            print("\n*** Simulating application restart by creating a new LLMService instance... ***\n")
            jarvis_restarted = LLMService(api_key=api_key, session_id=f"{session_id}_restarted", voice_handler=mock_voice)
            jarvis_restarted.set_current_project("project_test_alpha")

            print("\n[USER]: Based on our previous conversation, what was the class I asked you to create?")
            rag_result = jarvis_restarted.get_code_guidance_with_project_context(
                user_command="Based on our previous conversation, what was the class I asked you to create?",
                active_file_path="main.py", active_file_code="",
                project_context_files={}, user_project_goal="Model real-world objects."
            )
            print(f"LLM Response (RAG Test):\n{json.dumps(rag_result, indent=2)}\n")
            if "car" in rag_result.get("Guidance", "").lower() and "make" in rag_result.get("Guidance", "").lower():
                print("✅ LONG-TERM MEMORY (RAG) TEST: SUCCESS! The assistant recalled information from the saved file.")
            else:
                print("❌ LONG-TERM MEMORY (RAG) TEST: FAILED! The assistant could not retrieve the saved context.")

        finally:
            print("-" * 50)
            print(f"Test finished. Cleaning up temporary directory: {test_dir}")
            shutil.rmtree(test_dir)
            config.FAISS_STORE_PATH = original_path
            print("Cleanup complete.")
            print("-" * 50)

    run_test()