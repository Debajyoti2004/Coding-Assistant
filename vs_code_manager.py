import os
import subprocess
import sys
import time

class VsCodeHandler:
    def __init__(self, voice_manager):
        self.voice_manager = voice_manager

    def _run_vscode_command(self, command_args: list):
        is_windows = sys.platform == "win32"
        try:
            full_command = ["code", "-r"] + command_args
            subprocess.run(full_command, check=True, shell=is_windows)
            return True
        except FileNotFoundError:
            self.voice_manager.speak("Error: The 'code' command was not found. Please ensure VS Code is installed and in your system's PATH.")
            return False
        except subprocess.CalledProcessError as e:
            self.voice_manager.speak(f"There was an error executing the VS Code command: {e}")
            return False
        except Exception as e:
            self.voice_manager.speak(f"An unexpected error occurred: {e}")
            return False

    def create_and_open_file(self, full_path: str):
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            if not os.path.exists(full_path):
                with open(full_path, 'w') as f:
                    pass
                self.voice_manager.speak(f"File '{os.path.basename(full_path)}' created successfully.", tag='info')
            else:
                self.voice_manager.speak(f"File '{os.path.basename(full_path)}' already exists. Opening it.", tag='info')

            return self._run_vscode_command([full_path])

        except Exception as e:
            self.voice_manager.speak(f"I encountered an error while creating the file: {e}")
            return False

    def create_directory(self, full_path: str):
        try:
            if not os.path.exists(full_path):
                os.makedirs(full_path, exist_ok=True)
                self.voice_manager.speak(f"Directory '{os.path.basename(full_path)}' created.", tag='info')
                return True
            else:
                self.voice_manager.speak(f"Directory '{os.path.basename(full_path)}' already exists.", tag='info')
                return True
        except Exception as e:
            self.voice_manager.speak(f"I encountered an error creating the directory: {e}")
            return False

    def open_file_in_editor(self, full_path: str):
        if os.path.exists(full_path):
            return self._run_vscode_command([full_path])
        else:
            self.voice_manager.speak(f"Cannot open file because it does not exist at path: {full_path}")
            return False