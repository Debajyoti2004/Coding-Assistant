import os
import time
import json
from typing import List,Optional 

import config
from project_handler import ProjectManagerHandler
from voice_manager import VoiceHandler
from vs_code_manager import VsCodeHandler
from code_parser import CodeParser
from llm_core import LLMService 
from project_memory import ProjectMemory
from dotenv import load_dotenv
load_dotenv()

class CodeAssistant:
    def __init__(self,user_id:str,session_id:str): 
        self.voice_handler = VoiceHandler()
        self.project_manager = ProjectManagerHandler(voice_handler=self.voice_handler,base_dir = config.PROJECT_BASE_DIRECTORY)
        self.vscode_handler = VsCodeHandler(voice_manager = self.voice_handler)
        self.project_memory = ProjectMemory(faiss_path=config.FAISS_STORE_PATH,api_key=os.getenv("GOOGLE_API_KEY"))

        self.llm_service = LLMService(
            api_key = os.getenv("GOOGLE_API_KEY"),
            voice_handler=self.voice_handler,
            session_id = session_id ,
            user_id=user_id
        )
        self.project_dir = None
        self.code_parser = None
        self.project_goal = config.DEFAULT_PROJECT_GOAL 
        self.active_file_path = None
        self.last_llm_response = None 
        self.project_id = None
        self.session_id = session_id
        self.user_id = user_id

    def _get_file_content(self,file_path):
        if file_path and os.path.exists(file_path) and os.path.isfile(file_path):
            try: 
                with open(file_path,'r',encoding='utf-8') as f: 
                    return f.read()
            except Exception as e:
                self.voice_handler.speak(f"Error reading {os.path.basename(file_path)}.")
                print(f"File read error: {e}")
                return None
        return None
    
    def _write_file_content(self,file_path,content):
        if not file_path: 
            self.voice_handler.speak("Cannot write: No file path provided.")
            return False
        try: 
            os.makedirs(os.path.dirname(file_path),exist_ok=True)
            with open(file_path,'w',encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception as e: 
            self.voice_handler.speak(f"Error writing to {os.path.basename(file_path)}.")
            print(f"File write error: {e}")
            return False
        
    def _refresh_code_parser(self):
        if self.project_dir:
            self.code_parser = CodeParser(project_dir=self.project_dir)
        else:
            print("Warning: Project directory not set, cannot refresh code parser.")
        
    def _extract_argument_from_command(self, command_text: str, trigger_phrases: list[str], 
                                     prefix_keywords_to_strip: list[str] = None, 
                                     is_filename_extraction: bool = False) -> str | None:
        original_case_command_text = command_text 
        command_text_lower = command_text.lower()

        for trigger in trigger_phrases:
            trigger_lower = trigger.lower()
            trigger_start_index = command_text_lower.find(trigger_lower)

            if trigger_start_index != -1:
                argument_part_original_case = original_case_command_text[trigger_start_index + len(trigger):].strip()
                argument_part_lower = argument_part_original_case.lower()

                if not argument_part_original_case:
                    continue

                if prefix_keywords_to_strip:
                    for kw_prefix in prefix_keywords_to_strip:
                        kw_prefix_to_match = kw_prefix.lower()
                        if not kw_prefix_to_match.endswith(" ") and ' ' in kw_prefix:
                             kw_prefix_to_match_with_space = kw_prefix_to_match
                        elif not kw_prefix_to_match.endswith(" "):
                            kw_prefix_to_match_with_space = kw_prefix_to_match + " "
                        else:
                            kw_prefix_to_match_with_space = kw_prefix_to_match

                        if argument_part_lower.startswith(kw_prefix_to_match_with_space):
                            argument_part_original_case = argument_part_original_case[len(kw_prefix_to_match_with_space):].strip()
                            argument_part_lower = argument_part_original_case.lower()
                            break 
                
                if not argument_part_original_case:
                    continue

                words_original_case = argument_part_original_case.split()
                words_lower_case = argument_part_lower.split()
                
                extracted_arg_words_original_case = []
                stop_keywords = ["and", "then", "which", "that", "for", "with", "to", "also", "so", "because", "if", "please", "can", "could", "would", "make", "set", "change"]

                for i, word_orig in enumerate(words_original_case):
                    word_low = words_lower_case[i]
                    
                    if word_low in stop_keywords:
                        if extracted_arg_words_original_case:
                            break 
                        else: 
                            return None

                    extracted_arg_words_original_case.append(word_orig)
                    
                    if is_filename_extraction: 
                        if "." in word_orig and (i + 1 < len(words_lower_case) and words_lower_case[i+1] in stop_keywords):
                            break
                
                if extracted_arg_words_original_case:
                    final_argument = " ".join(extracted_arg_words_original_case).strip()
                    if final_argument.endswith(".") and not (is_filename_extraction and "." in final_argument[:-1]):
                        final_argument = final_argument[:-1].strip()
                    
                    if final_argument:
                        return final_argument
        return None
    
    def _handle_llm_output(self,llm_response_dict):
        if isinstance(llm_response_dict,dict):
            if "Error" in llm_response_dict:
                error_message = llm_response_dict["Error"]
                raw_response_info = llm_response_dict.get("RawResponse")
                full_error_spoken = error_message
                if raw_response_info:
                    print(f"LLM Error with Raw Response: {raw_response_info}")
                self.voice_handler.speak(full_error_spoken)
                self.last_llm_response = None 
                return False

            guidance_text = llm_response_dict.get("Guidance")
            suggested_code = llm_response_dict.get("Suggested code")

            spoken_something = False
            if guidance_text:
                self.voice_handler.speak(guidance_text)
                spoken_something = True
            
            if suggested_code and isinstance(suggested_code, str) and suggested_code.lower() != 'none' and suggested_code.strip():
                self.last_llm_response = suggested_code 
                if not spoken_something: 
                    self.voice_handler.speak("I have a code suggestion for you:")
                print("\n--- Suggested Code ---")
                print(suggested_code)
                print("--- End Suggested Code ---\n")
                if len(suggested_code) < 200:
                    self.voice_handler.speak(suggested_code)
                else:
                    self.voice_handler.speak("The code is a bit long, so I've printed it to the console.")
                spoken_something = True
            else:
                self.last_llm_response = None 

            if not spoken_something:
                self.voice_handler.speak("I processed your request, but didn't have specific guidance or code to provide this time.")
            return True 
        else:
            self.voice_handler.speak(str(llm_response_dict))
            print(f"Unexpected LLM service response format: {llm_response_dict}")
            self.last_llm_response = None
            return False

    def setup_project(self):
        self.voice_handler.speak("Welcome! Let's set up your coding project.")
        project_name_prompt = f"What's the project name? or say 'default' for '{config.DEFAULT_PROJECT_NAME}'."
        project_name_input = self.voice_handler.listen(project_name_prompt,timeout_seconds=8,phrase_time_limit_seconds=5)

        if not project_name_input:
            self.voice_handler.speak("I did not hear the project name. Please type your project name.")
            project_name_input = input("Project Name:")

        project_name = project_name_input.strip() if project_name_input and 'default' not in project_name_input.lower() else config.DEFAULT_PROJECT_NAME
        self.project_dir = self.project_manager.create_project_folder(project_name)
        if not self.project_dir:
            self.voice_handler.speak("Project setup failed. Exiting.")
            raise SystemExit("Project directory setup failed.")

        self._refresh_code_parser() 

        if self.project_manager.open_vscode_in_folder(self.project_dir):
            self.voice_handler.speak("VS Code is opening. Please make sure the Explorer panel is ready.")
            time.sleep(6) 
        else: 
            self.voice_handler.speak("Could not open VS Code automatically. Please Open it manually in the project directory.")
            time.sleep(3)

        goal_prompt = f"What's the main goal for '{project_name}'? You can also say 'default goal'."
        goal_input = self.voice_handler.listen(goal_prompt,timeout_seconds=12,phrase_time_limit_seconds = 8) 
        if not goal_input:
            self.voice_handler.speak("Did not hear project goal. Please type project goal.")
            goal_input = input("Project Goal: ")

        if goal_input and 'default' not in goal_input.lower() and goal_input.strip():
            self.project_goal = goal_input.strip()
        else: 
            self.project_goal = config.DEFAULT_PROJECT_GOAL 
        self.voice_handler.speak(f"Project '{project_name}' is ready. Goal: {self.project_goal}")
        self.project_id = self.llm_service.set_current_project(project_id=project_name)

    def handle_command(self,command:str):
        original_command = command 
        command_lower = command.lower()

        if not self.project_dir or not self.code_parser:
            self.voice_handler.speak("Project isn't initialized. Please restart.")
            return True
        
        if any(cmd in command_lower for cmd in ["create file","create a file","make a file","make file"]):
            trigger_phrases = ["create file", "create a file", "make a file", "make file"] 
            prefix_keywords = ["named","called","with name","as ","a ","an ","the "]

            file_name = self._extract_argument_from_command(original_command,trigger_phrases,prefix_keywords,is_filename_extraction = True) 

            if not file_name:
                self.voice_handler.speak("Okay, what's the full file name, like 'script.py'? ")
                file_name = self.voice_handler.listen("File name?")

            if file_name:
                file_name = file_name.replace(" ","_").strip()
                if not self.vscode_handler.hover_on_explorer_target(config.VSCODE_PROJECT_EXPLORER_TARGET_IMG_PATH): 
                    self.voice_handler.speak("Couldn't find the project in VS Code Explorer to create the file.")
                    return True
                if self.vscode_handler.click_on_file_button(file_name):
                    self.active_file_path = os.path.join(self.project_dir, file_name) 
                    self._write_file_content(self.active_file_path,"") 
                    self._refresh_code_parser() 
                    self.voice_handler.speak(f"{file_name} created and is now active.")
                else: 
                    self.voice_handler.speak(f"Failed to create file {file_name} via VS Code.")
            else: 
                self.voice_handler.speak("File name not provided or understood.")
            return True 

        elif any(phrase in command_lower for phrase in ["create directory", "create folder", "make folder", "make directory","make a folder","make a directory","create a folder","create a directory"]):
            trigger_phrases = ["create directory","create folder","make directory","make folder", "make a folder","make a directory","create a folder","create a directory"]
            prefix_keywords = ["named","called","as ","a ","an ","the "]
            dir_name = self._extract_argument_from_command(original_command,trigger_phrases,prefix_keywords) 

            if not dir_name:
                self.voice_handler.speak("Okay, What's directory name?")
                dir_name = self.voice_handler.listen("Directory name?")
            if dir_name:
                dir_name = dir_name.replace(" ","_").strip()
                if not self.vscode_handler.hover_on_explorer_target(config.VSCODE_PROJECT_EXPLORER_TARGET_IMG_PATH): 
                    self.voice_handler.speak("Couldn't find the project in VS Code Explorer to create the directory")
                    return True
                if self.vscode_handler.click_on_dir_button(dir_name):
                    self._refresh_code_parser()
                    self.voice_handler.speak(f"Directory {dir_name} created.")
                else: 
                    self.voice_handler.speak(f"Failed to create directory {dir_name} via VS Code.")
            else: 
                self.voice_handler.speak("Directory name not provided or understood.")
            return True 

        elif any(phrase in command_lower for phrase in [
                "open file", 
                "switch to file", 
                "go to file",
                "show me file", 
                "show me the file"
            ]) or (command_lower.startswith("open ") and len(command_lower.split()) > 1):
            trigger_phrases = ["open file","switch to file","go to file","open ","show me file","show me the file"]
            prefix_keywords = ["named","called","the ","a "]
            file_name_to_open = self._extract_argument_from_command(original_command,trigger_phrases,prefix_keywords,is_filename_extraction=True) 

            if not file_name_to_open:
                self.voice_handler.speak("Okay, which file to open?")
                file_name_to_open = self.voice_handler.listen("File to open?")
            
            if file_name_to_open:
                file_name_to_open = file_name_to_open.strip()
                found_path = None
                exact_match_in_project = False 
                if self.code_parser and self.code_parser.all_files:
                    for rel_path,abs_path in self.code_parser.all_files.items():
                        if os.path.basename(rel_path).lower() == file_name_to_open.lower() and os.path.isfile(abs_path):
                            found_path = abs_path
                            exact_match_in_project = True
                            break
                
                if self.vscode_handler.go_to_folder_by_name(folder_name=found_path):
                    if exact_match_in_project and found_path:
                        self.active_file_path = found_path
                        self.voice_handler.speak(f"Switched to {os.path.basename(found_path)}.")
                    else:
                        potential_path = os.path.join(self.project_dir, file_name_to_open)
                        if os.path.exists(potential_path) and os.path.isfile(potential_path):
                            self.active_file_path = potential_path
                            self.voice_handler.speak(f"Opened {file_name_to_open}. It's now active.")
                            self._refresh_code_parser() 
                        else:
                            self.voice_handler.speak(f"VS Code attempted to open {file_name_to_open}. If it's a new file or outside the project, I may not track it as active immediately.")
                            self.active_file_path = None 
                else:
                    self.voice_handler.speak(f"Could not open {file_name_to_open} via VS Code. Does it exist?")
            else: 
                self.voice_handler.speak("No file name provided to open.")
            return True 

        elif any(phrase in command_lower for phrase in ["what is the name of active file", "what is the active file", "current file"]):
            if self.active_file_path and os.path.exists(self.active_file_path):
                self.voice_handler.speak(f"Active file is {os.path.basename(self.active_file_path)}.")
            else:
                self.voice_handler.speak("No file is currently active, or the path is invalid.")
            return True

        elif any(phrase in command_lower for phrase in ["show active file","show me active file","show me the active file", "read active file", "read the active file"]):
            if self.active_file_path:
                content = self._get_file_content(self.active_file_path)
                if content is not None: 
                    self.voice_handler.speak(f"Content of {os.path.basename(self.active_file_path)}:")
                    print(content)
                    if len(content) > 250: 
                        self.voice_handler.speak("It's quite long, printed to console.")
                    elif content.strip() == "": 
                        self.voice_handler.speak("The file is empty.")
                    else: 
                        self.voice_handler.speak(content)
                else: 
                    self.voice_handler.speak(f"Could not read content of {os.path.basename(self.active_file_path)}.")
            else:
                self.voice_handler.speak("No active file to read.")
            return True

        elif "list files" in command_lower or "project structure" in command_lower:
            if self.code_parser and self.code_parser.all_files:
                self.voice_handler.speak("Project files and directories are:")
                for rel_path_key in self.code_parser.all_files.keys(): 
                    print(rel_path_key) 
                self.voice_handler.speak("The list is in the console.")
            else:
                self.voice_handler.speak("No files found or project not parsed.")
            return True

        elif any(kw in command_lower for kw in ["analyze","help","review","explain","debug","what's wrong","understand","remind me", "what did you say", "previous response", "check your last suggestion"]):
            requires_active_file_explicitly = any(phrase in command_lower for phrase in ["this code", "this file", "the active file", "current file"]) \
                                           and not any(mem_kw in command_lower for mem_kw in ["remind me", "what did you say", "previous response"])

            if requires_active_file_explicitly and (not self.active_file_path or not os.path.exists(self.active_file_path)):
                self.voice_handler.speak("To help with 'this code' or 'this file', Please open a file first.")
                return True
            
            active_file_code_for_llm = "" 
            active_file_path_for_llm = "None"

            if self.active_file_path and os.path.exists(self.active_file_path):
                active_file_code_for_llm = self._get_file_content(self.active_file_path)
                active_file_path_for_llm = self.active_file_path
            elif any(mem_kw in command_lower for mem_kw in ["remind me", "what did you say", "previous response"]):
                 active_file_code_for_llm = "User is asking about previous interaction. Current file context might be less relevant."
            elif not requires_active_file_explicitly: 
                active_file_code_for_llm = "No specific file is active for this general query. User is asking for broader help or explanation."
            
            context_files_content = {}
            if self.code_parser and self.active_file_path and os.path.exists(self.active_file_path):
                imports = self.code_parser.extract_imports_from_file(self.active_file_path)
                if "Error" not in imports : 
                    resolved_paths = self.code_parser.resolve_import_paths(imports)
                    if "Error" not in resolved_paths: 
                        for rel_path_key, abs_path_val in resolved_paths.items(): 
                            if abs_path_val != self.active_file_path:
                                content = self._get_file_content(abs_path_val)
                                if content is not None:
                                    context_files_content[rel_path_key] = content
            
            self.voice_handler.speak("Okay, let me think about that... One moment.")
            llm_response_dict = self.llm_service.get_code_guidance_with_project_context(
                user_command=original_command, 
                active_file_path=active_file_path_for_llm,
                active_file_code=active_file_code_for_llm if active_file_code_for_llm else "No specific file content available for this request.",
                project_context_files=context_files_content,
                user_project_goal=self.project_goal
            )
            self._handle_llm_output(llm_response_dict)
            return True
        
        elif "write this" in command_lower or "apply this" in command_lower or "put that in file" in command_lower:
            if self.last_llm_response: 
                if self.active_file_path:
                    self.voice_handler.speak(f"Applying changes to {os.path.basename(self.active_file_path)}.")
                    code_to_write = self.last_llm_response 
                    
                    if self._write_file_content(self.active_file_path, code_to_write):
                        if self.vscode_handler.refresh_open_file_tab():
                            self.voice_handler.speak("Content written and VS Code refreshed.")
                        else:
                            self.voice_handler.speak("Content written, but failed to refresh VS Code tab automatically.")
                    else:
                        self.voice_handler.speak("Failed to write to the file.")
                else:
                    self.voice_handler.speak("No active file selected to write to.")
            else:
                self.voice_handler.speak("I don't have a previous code suggestion to write. Please ask for one first.")
            return True

        elif "clear chat" in command_lower or "reset conversation" in command_lower:
            if self.llm_service: 
                self.llm_service.clear_conversation_memory()
            self.last_llm_response = None 
            return True

        elif "exit" in command_lower or "quit" in command_lower or "stop" in command_lower:
            self.voice_handler.speak("Goodbye!")
            return False 
        
        elif any(phase in command_lower for phase in ["previous chat on this project","previous chat on current project","previous chat on active project","previous chat on my project"]):
            result = self.project_memory.load_chat_on_current_project(
                command_query=command_lower,
                user_id=self.user_id,
                project_id=self.project_id,
                k=20
            )
            self.voice_handler.speak("Here is your all previous chat on this project")
            print(result)
            return True
        
        elif any(phase in command_lower for phase in ["previous chat on this session","chat on this session"]):
            result = self.project_memory.load_chat_for_user_session(
                command_query=command_lower,
                user_id=self.user_id,
                session_id=self.session_id,
                k=20
            )
            self.voice_handler.speak("Here is your all previous chat on this session")
            print(result)
            return True
        
        elif command_lower: 
            active_file_code_for_llm = ""
            active_file_path_for_llm = "None"
            if self.active_file_path and os.path.exists(self.active_file_path):
                active_file_code_for_llm = self._get_file_content(self.active_file_path)
                active_file_path_for_llm = self.active_file_path
            
            context_files_content = {}
            if self.code_parser and self.active_file_path and os.path.exists(self.active_file_path):
                imports = self.code_parser.extract_imports_from_file(self.active_file_path)
                if "Error" not in imports :
                    resolved_paths = self.code_parser.resolve_import_paths(imports)
                    if "Error" not in resolved_paths:
                        for rel_path_key, abs_path_val in resolved_paths.items():
                            if abs_path_val != self.active_file_path:
                                content = self._get_file_content(abs_path_val)
                                if content is not None:
                                    context_files_content[rel_path_key] = content
            
            self.voice_handler.speak("Let me see what I can do with that...") 
            llm_response_dict = self.llm_service.get_code_guidance_with_project_context(
                user_command=original_command, 
                active_file_path=active_file_path_for_llm,
                active_file_code=active_file_code_for_llm if active_file_code_for_llm else "File is empty or not selected.",
                project_context_files=context_files_content,
                user_project_goal=self.project_goal
            )
            self._handle_llm_output(llm_response_dict)
            return True 
        
        return True 
    
    def run(self):
        try:
            self.setup_project()
        except SystemExit:
            return
        except Exception as e:
            self.voice_handler.speak(f"A critical error occurred during setup: {e}. Please check the console.")
            print(f"Setup error: {e}")
            return

        self.voice_handler.speak("I'm ready for your commands.")
        running = True
        while running:
            user_input_text = ""
            try:
                raw_command = self.voice_handler.listen("Listening...", timeout_seconds=20, phrase_time_limit_seconds=12) 

                if raw_command:
                    user_input_text = raw_command.strip()
                    if user_input_text:
                         running = self.handle_command(user_input_text)
                else: 
                    time.sleep(0.5) 

            except KeyboardInterrupt:
                self.voice_handler.speak("Exiting now.")
                running = False
            except Exception as e:
                self.voice_handler.speak(f"An unexpected error occurred in the main loop. Please check the console.")
                print(f"Runtime Error: {e} during command: {user_input_text}")
                time.sleep(1) 