
import os
import subprocess

class ProjectManagerHandler:
    DEFAULT_PROJECT_BASE_DIR = os.path.expanduser("~/Desktop/VoiceAssistedProjects")

    def __init__(self, voice_handler, base_dir=None):
        self.voice_handler = voice_handler
        self.project_base_dir = base_dir if base_dir else ProjectManagerHandler.DEFAULT_PROJECT_BASE_DIR

    def create_project_folder(self, project_name):
        if not project_name:
            self.voice_handler.speak("No project name provided.")
            return None
        
        project_path = os.path.join(self.project_base_dir, project_name)

        try:
            if not os.path.exists(self.project_base_dir):
                os.makedirs(self.project_base_dir)
                self.voice_handler.speak(f"Created base directory at {self.project_base_dir}")

            if os.path.exists(project_path):
                self.voice_handler.speak(f"Project folder '{project_name}' already exists at {project_path}.")
                return project_path
            
            os.makedirs(project_path)
            self.voice_handler.speak(f"Successfully created project folder '{project_name}' at {project_path}.")
            return project_path
        except Exception as e:
            self.voice_handler.speak(f"Error creating project folder '{project_name}': {e}")
            return None

    def open_vscode_in_folder(self, folder_path):
        if not folder_path or not os.path.isdir(folder_path):
            self.voice_handler.speak(f"Invalid folder path: {folder_path}")
            return False
        
        try:
            self.voice_handler.speak(f"Opening VS Code in {folder_path}...")
            subprocess.run(["code", folder_path], check=True, shell=False)
            self.voice_handler.speak("VS Code should now be open.")
            return True
        except FileNotFoundError:
            self.voice_handler.speak("Error: The 'code' command was not found. Make sure VS Code is installed and 'code' is in your system's PATH.")
            return False
        except subprocess.CalledProcessError as e:
            self.voice_handler.speak(f"Error opening VS Code: {e}")
            return False
        except Exception as e:
            self.voice_handler.speak(f"An unexpected error occurred while trying to open VS Code: {e}")
            return False