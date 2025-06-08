import os
import time
import re
from dotenv import load_dotenv

from code_assistant_gui import CodeAssistantGUI
import config
from project_handler import ProjectManagerHandler
from vs_code_manager import VsCodeHandler
from code_parser import CodeParser
from llm_core import LLMService
from project_memory import ProjectMemory

from faster_whisper import WhisperModel
import sounddevice as sd
import numpy as np
import pyttsx3

# os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

load_dotenv()

def split_into_subcommands(command: str):
    pattern = r"\b(?:first|then|after that|and then|next|afterwards|subsequently)\b"
    parts = re.split(pattern, command, flags=re.IGNORECASE)
    cleaned_parts = [part.strip(" ,.") for part in parts if part.strip()]
    return cleaned_parts if len(cleaned_parts) > 1 else [command.strip()]

class CodeAssistant:
    def __init__(self, ui: CodeAssistantGUI, user_id: str, session_id: str):
        self.ui = ui
        self.whisper_model = None
        self.tts_engine = None
        self.user_id = user_id
        self.session_id = session_id

        try:
            self.ui.update_status("Loading Text-to-Speech engine...")
            self.tts_engine = pyttsx3.init()
        except Exception as e:
            self.ui.update_status(f"TTS disabled: {e}")

        try:
            self.ui.update_status("Loading AI speech model...")
            self.whisper_model = WhisperModel(model_size_or_path="base.en", device="cpu", compute_type="int8")
        except Exception as e:
            self.ui.update_status(f"Whisper disabled: {e}")

        self.project_memory = ProjectMemory(api_key=os.getenv("GOOGLE_API_KEY"))
        self.llm_service = LLMService(api_key=os.getenv("GOOGLE_API_KEY"), voice_handler=self, session_id=session_id, user_id=user_id)
        self.project_manager = ProjectManagerHandler(voice_handler=self, base_dir=config.PROJECT_BASE_DIRECTORY)
        self.vscode_handler = VsCodeHandler(voice_manager=self)
        
        self.project_dir = None
        self.code_parser = None
        self.project_goal = config.DEFAULT_PROJECT_GOAL
        self.active_file_path = None
        self.last_llm_response = None
        self.project_id = None

    def speak(self, text: str, tag: str = 'assistant'):
        if not text: return
        self.ui.add_log(text, tag)
        if self.tts_engine:
            self.ui.start_speaking_animation()
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            finally:
                self.ui.stop_speaking_animation()

    def listen(self, prompt: str):
        self.ui.update_status(f"🎤 {prompt}")
        
        start_time = time.time()
        while time.time() - start_time < 10:
            text_input = self.ui.get_user_text_input()
            if text_input:
                self.ui.add_log(text_input, tag='user')
                return text_input.lower()
            time.sleep(0.1)

        if self.whisper_model:
            self.ui.update_status("Listening for voice...")
            try:
                samplerate = 16000
                recording = sd.rec(int(5 * samplerate), samplerate=samplerate, channels=1, dtype='float32')
                sd.wait()
                segments, _ = self.whisper_model.transcribe(recording.flatten(), vad_filter=True)
                text = " ".join(segment.text for segment in segments).strip()
                if text:
                    self.ui.add_log(text, tag='user')
                    return text.lower()
            except Exception as e:
                self.ui.update_status(f"Voice recognition failed: {e}")

        return None

    def _get_file_content(self, file_path):
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                self.speak(f"Error reading {os.path.basename(file_path)}: {e}")
        return ""

    def _write_file_content(self, file_path, content):
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding="utf-8") as f:
                f.write(content)
            
            self.vscode_handler.open_file_in_editor(file_path)
            
            return True
        except Exception as e:
            self.speak(f"Error writing to {os.path.basename(file_path)}: {e}")
        return False

    def _refresh_code_parser(self):
        if self.project_dir:
            self.code_parser = CodeParser(project_dir=self.project_dir)
            self.speak("Project file structure has been refreshed.")

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
    
    def _extract_path_from_command(self, command: str, command_type: str) -> dict:
        command_lower = command.lower()
        result = {'name': None, 'parent': None}
        pattern = re.compile(
            rf".*(?:named|called)\s+([\w\.\/\\_]+)\s+(?:under|in|inside)\s+([\w\.\/\\_]+)",
            re.IGNORECASE
        )
        match = pattern.match(command_lower)
        if match:
            result['name'] = match.group(1)
            result['parent'] = match.group(2)
        else:
            if command_type == 'file':
                keyword = "file"
            else:
                keyword = "directory"
            name_pattern = re.compile(rf"create\s+(?:a\s+)?{keyword}\s+(?:named|called)?\s*([\w\.\/\\_]+)", re.IGNORECASE)
            name_match = name_pattern.search(command_lower)
            if name_match:
                result['name'] = name_match.group(1)
        return result
    
    def _handle_llm_output(self, llm_response_dict):
        if not isinstance(llm_response_dict, dict):
            self.speak(str(llm_response_dict), 'info')
            self.last_llm_response = None
            return False
        if "Error" in llm_response_dict:
            self.speak(llm_response_dict["Error"])
            return False
        guidance_text = llm_response_dict.get("Guidance")
        suggested_code = llm_response_dict.get("Suggested code")
        if guidance_text:
            self.speak(guidance_text)
        if suggested_code and suggested_code.strip().lower() != 'none':
            self.last_llm_response = suggested_code
            if not guidance_text: self.speak("I have a code suggestion:")
            self.ui.add_log(suggested_code, tag='code')
        else:
            self.last_llm_response = None
        return True

    def setup_project(self):
        self.speak("Welcome! I am Jarvis, your coding assistant.")
        project_name = self.listen("What is the name of the project we'll be working on? 'You can also say 'default' to use the default project name.")
        if not project_name:
            self.speak("No project name provided. Shutting down.")
            raise SystemExit("Project setup cancelled by user.")
        
        project_name = project_name if 'default' not in project_name else config.DEFAULT_PROJECT_NAME
        self.project_dir = self.project_manager.create_project_folder(project_name)
        if not self.project_dir: raise SystemExit("Project setup failed.")
        
        self.project_id = self.llm_service.set_current_project(project_id=project_name)
        self._refresh_code_parser()
        self.project_manager.open_vscode_in_folder(self.project_dir)
        time.sleep(5)
        
        goal_input = self.listen(f"What is the main goal for the '{project_name}' project? 'You can also say 'default' to use the default goal.")
        self.project_goal = goal_input if 'default' not in goal_input else config.DEFAULT_PROJECT_GOAL
        self.speak(f"Project '{project_name}' is ready. Goal: {self.project_goal}")
    
    def set_active_file(self, file_path: str):
        if file_path and os.path.exists(file_path):
            self.active_file_path = file_path
            self._refresh_code_parser()
            self.vscode_handler.open_file_in_editor(file_path)
            self.speak(f"Active file set to {os.path.basename(file_path)}.")
        else:
            self.speak("Invalid file path provided. Active file not set.")

    def set_project_goal(self, goal: str):
        if goal:
            self.project_goal = goal
            self.speak(f"Project goal updated to: {goal}")
        else:
            self.speak("No goal provided. Project goal not updated.")
    
    def get_active_file_path(self):
        if self.active_file_path and os.path.exists(self.active_file_path):
            return self.active_file_path
        else:
            self.speak("No active file set or the file does not exist.")
            return None
        
    def handle_command(self, command: str):
        command_lower = command.lower()
        
        if any(cmd in command_lower for cmd in ["create file", "make file"]):
            path_info = self._extract_path_from_command(command, "file")
            file_name = path_info.get('name')
            parent_dir = path_info.get('parent')

            if not file_name:
                file_name = self.listen("What should the file be named?")
            if not parent_dir:
                parent_dir = self.listen("Where should I create this file? (e.g., 'src/utils' or just press Enter for the root)")
            
            if file_name:
                base_path = self.project_dir
                if parent_dir and os.path.exists(os.path.join(self.project_dir, parent_dir)):
                    base_path = os.path.join(self.project_dir, parent_dir)
                
                full_path = os.path.join(base_path, file_name)
                if self.vscode_handler.create_and_open_file(full_path):
                    self.active_file_path = full_path
                    self._refresh_code_parser()
                    self.speak(f"Created file '{file_name}' inside '{os.path.relpath(base_path, self.project_dir)}'.")
            return True
        
        elif any(phrase in command_lower for phrase in ["create directory", "create folder"]):
            path_info = self._extract_path_from_command(command, "directory")
            dir_name = path_info.get('name')
            parent_dir = path_info.get('parent')

            if not dir_name:
                dir_name = self.listen("What should the directory be named?")
            
            base_path = self.project_dir
            if parent_dir:
                prospective_parent_path = os.path.join(self.project_dir, parent_dir)
                if os.path.exists(prospective_parent_path):
                    base_path = prospective_parent_path
                else:
                    self.speak(f"Parent directory '{parent_dir}' doesn't exist. Creating '{dir_name}' in the root.")
            
            full_path = os.path.join(base_path, dir_name)
            if self.vscode_handler.create_directory(full_path):
                self._refresh_code_parser()
                self.speak(f"Created directory '{dir_name}' inside '{os.path.relpath(base_path, self.project_dir)}'.")
            return True

        elif any(phrase in command_lower for phrase in ["open file", "go to file", "switch to file"]) or (command_lower.startswith("open ") and len(command_lower.split()) > 1):
            file_to_open = self._extract_argument_from_command(command, ["open file", "go to file", "switch to file", "open "], ["the ","a "], True)
            if not file_to_open: file_to_open = self.listen("Which file should I open?")
            if file_to_open:
                found_path = next((path for path in self.code_parser.get_all_files().values() if file_to_open in os.path.basename(path)), None)
                if found_path and self.vscode_handler.open_file_in_editor(found_path):
                    self.active_file_path = found_path
                    self.speak(f"Switched to {os.path.basename(found_path)}.")
                else:
                    self.speak(f"Sorry, I couldn't find the file '{file_to_open}'.")
            return True
        
        elif "list files" in command_lower or "project structure" in command_lower:
            structure = "\n".join(self.code_parser.get_all_files().keys()) if self.code_parser else "Not available."
            self.speak("Current project structure:", tag='info')
            self.ui.add_log(structure, tag="assistant")
            return True

        elif any(kw in command_lower for kw in ["analyze", "help", "review", "explain", "debug"]):
            self.speak("Thinking...")
            active_code = self._get_file_content(self.active_file_path) if self.active_file_path else "No active file."
            import_files = self.code_parser.extract_imports_from_file(self.active_file_path) if self.active_file_path else {}
            import_paths = self.code_parser.resolve_import_paths(import_files) if self.active_file_path else {}
            
            project_context_files = {}
            for rel_path, abs_path in import_paths.items():
                content = self._get_file_content(abs_path)
                if content:
                    project_context_files[rel_path] = content
                    
            llm_response = self.llm_service.get_code_guidance_with_project_context(
                user_command=command, active_file_path=self.active_file_path or "None",
                active_file_code=active_code, project_context_files=project_context_files, user_project_goal=self.project_goal
            )
            self._handle_llm_output(llm_response)
            return True

        elif any(cmd in command_lower for cmd in ["write this", "apply this"]):
            if self.last_llm_response and self.active_file_path:
                self.speak(f"Applying changes to {os.path.basename(self.active_file_path)}...")
                if self._write_file_content(self.active_file_path, self.last_llm_response):
                    self.speak("Content written successfully.")
            else:
                self.speak("No suggestion to write or no active file.")
            return True
        
        elif any(phrase in command_lower for phrase in ["get active file", "current active file", "active file"]):
            if self.active_file_path and os.path.exists(self.active_file_path):
                self.speak(f"The current active file is {os.path.basename(self.active_file_path)}.")
            else:
                self.speak("No active file set or the file does not exist.")
            return True
        
        elif any(phrase in command_lower for phrase in ["set goal", "update goal", "change goal"]):
            new_goal = self._extract_argument_from_command(command, ["set goal", "update goal", "change goal"], ["to ", "as "])
            if not new_goal: new_goal = self.listen("What is the new project goal?")
            if new_goal:
                self.set_project_goal(new_goal)
            return True
        
        elif any(phrase in command_lower for phrase in ["set active file", "switch active file", "change active file"]):
            new_active_file = self._extract_argument_from_command(command, ["set active file", "switch active file", "change active file"], ["to ", "as "], True)
            if not new_active_file: new_active_file = self.listen("What is the new active file?")
            if new_active_file:
                found_path = next((path for path in self.code_parser.get_all_files() if new_active_file in os.path.basename(path)), None)
                if found_path:
                    self.set_active_file(found_path)
                else:
                    self.speak(f"Could not find the file '{new_active_file}'.")
            return True
        
        elif any(phrase in command_lower for phrase in ["save conversation", "remember this"]):
            self.llm_service.save_conversation_to_long_term_memory()
            return True
            
        elif any(phrase in command_lower for phrase in ["clear history", "fresh start"]):
            self.llm_service.clear_conversation_memory()
            return True

        elif "exit" in command_lower or "quit" in command_lower:
            self.speak("Goodbye!")
            return False
        
        else:
            self.speak("Let me see what I can do with that...")
            active_code = self._get_file_content(self.active_file_path)
            llm_response = self.llm_service.get_code_guidance_with_project_context(
                user_command=command, 
                active_file_path=self.active_file_path,
                active_file_code=active_code, 
                project_context_files={},
                user_project_goal=self.project_goal
            )
            self._handle_llm_output(llm_response)
            return True

    def run(self):
        try:
            self.setup_project()
        except SystemExit as e:
            self.speak(f"Shutting down. {e}")
            return
        
        self.speak("I'm ready for your commands.")
        running = True
        while running:
            command = self.listen("Listening for your next command...")
            command = command.lower().strip() if command else ""
            if command:
                subcommands = split_into_subcommands(command)
                for sub in subcommands:
                    if not self.handle_command(sub):
                        running = False
                        break
            else:
                time.sleep(0.1)