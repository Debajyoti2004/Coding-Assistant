import threading
from code_assistant_gui import CodeAssistantGUI
from code_assistant import CodeAssistant
import os

def main_code_assistant():
    ui = CodeAssistantGUI()
    user_id = "default_user"
    session_id = "default_session"
    assistant = CodeAssistant(ui=ui, user_id=user_id, session_id=session_id)

    logic_thread = threading.Thread(target=assistant.run, daemon=True)
    logic_thread.start()

    ui.start()

if __name__ == "__main__":
    main_code_assistant()