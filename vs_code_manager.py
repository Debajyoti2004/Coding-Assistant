import pyautogui
import time
import os
import platform
import config

class VsCodeHandler:
    def __init__(self,voice_manager):
        self.voice_manager = voice_manager
        self.ctrl_cmd = 'command' if platform.system() == 'Darwin' else 'ctrl'

        pyautogui.FAILSAFE = True
        self.create_file_button = config.VSCODE_CREATE_FILE_BUTTON_IMG_PATH
        self.create_dir_button = config.VSCODE_CREATE_DIR_BUTTON_IMG_PATH

        self.default_type_interval = 0.03
        self.short_delay = 0.3
        self.medium_delay = 0.7
        self.long_delay = 1.2
        self.image_confidence = 0.85

    def hover_on_explorer_target(self,target_hover_image):
        try: 
            target_location = pyautogui.locateCenterOnScreen(
                image = target_hover_image,
                confidence=self.image_confidence,
                grayscale = True
            )
            pyautogui.moveTo(target_location.x,target_location.y,duration=0.25)
            time.sleep(self.medium_delay)
            return True 
        
        except Exception as e: 
            print(f"Error occured during hovering on project folder: {e}")
            return False
        
    def click_on_file_button(self,item_name_to_type):
        try: 
            target_location = pyautogui.locateCenterOnScreen(
                image = self.create_file_button,
                confidence = self.image_confidence,
                grayscale=True
            )
            pyautogui.click(target_location.x,target_location.y)
            time.sleep(self.medium_delay)

            self.voice_manager.speak(f"Typing '{item_name_to_type}'.")
            pyautogui.typewrite(item_name_to_type, interval=self.default_type_interval)
            time.sleep(self.short_delay)
            pyautogui.press('enter')
            time.sleep(self.long_delay)

            self.voice_manager.speak(f"'{item_name_to_type}' should now be created in Explorer.")
            return True
        
        except Exception as e: 
            print(f"Error: Clicking on file button == {e}")
            self.voice_manager.speak(f"Error: Clicking on file button == {e}")
            return False
        
    def click_on_dir_button(self,item_name_to_type):
        try: 
            target_location = pyautogui.locateCenterOnScreen(
                image=self.create_dir_button,
                confidence = self.image_confidence,
                grayscale = True
            )
            pyautogui.click(target_location.x,target_location.y)
            time.sleep(self.medium_delay)

            self.voice_manager.speak(f"Typing '{item_name_to_type}'.")
            pyautogui.typewrite(item_name_to_type,interval = self.default_type_interval)
            time.sleep(self.short_delay)
            pyautogui.press("enter")

            self.voice_manager.speak(f"'{item_name_to_type}' should now be created in Explorer.")
            return True 
        
        except Exception as e: 
            print(f"Error occured on clicking directory:{e}")
            return False
        
    def refresh_open_file_tab(self):
        self.voice_manager.speak("Refreshing the open file from disk.")
        try:
            pyautogui.hotkey(self.ctrl_cmd, 'shift', 'p')
            time.sleep(self.medium_delay)
            pyautogui.typewrite("File: Revert File", interval=self.default_type_interval)
            time.sleep(self.short_delay)
            pyautogui.press('enter')
            time.sleep(self.medium_delay)
            self.voice_manager.speak("Open file has been refreshed from disk.")
            return True

        except Exception as e:
            self.voice_manager.speak(f"VS Code automation error (Revert File): {e}")
            return False
        
    def go_to_folder_by_name(self,folder_name):
        try: 
            pyautogui.hotkey(self.ctrl_cmd, 'p')  
            time.sleep(0.5)
            pyautogui.typewrite(folder_name, interval=0.03)
            time.sleep(0.5)
            pyautogui.press('enter')
            print(f"✅ Navigated to '{folder_name}'.")
            return True
        
        except Exception as e:
            print(f"Navigation Problem for {folder_name}")
            return False






        



            

            



