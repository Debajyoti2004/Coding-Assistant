import tkinter as tk
from tkinter import scrolledtext
import queue
import screeninfo
import random

class Colors:
    BACKGROUND = "#1e1e2e"
    FRAME_BORDER = "#89b4fa"
    HEADER_TEXT = "#89b4fa"
    USER_TEXT = "#f5c2e7"
    ASSISTANT_TEXT = "#a6e3a1"
    INFO_TEXT = "#cdd6f4"
    INPUT_BG = "#313335"
    VOICE_BAR_ACTIVE = "#00f5d4"
    VOICE_BAR_SILENT = "#45475a"

class CodeAssistantGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Code Assistant")

        width = 550
        height = 700
        screen = screeninfo.get_monitors()[0]
        x = screen.width - width - 40
        y = screen.height - height - 80
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.configure(bg=Colors.BACKGROUND)
        self.root.attributes('-alpha', 0.95)

        self.user_input_queue = queue.Queue()
        self.is_animating = False
        self._build_ui()

    def _build_ui(self):
        main_frame = tk.Frame(self.root, bg=Colors.BACKGROUND)
        main_frame.pack(expand=True, fill="both", padx=10, pady=10)
        main_frame.config(highlightbackground=Colors.FRAME_BORDER, highlightthickness=1)

        header = tk.Label(main_frame, text="🧠 Code Assistant", font=("Segoe UI", 14, "bold"), fg=Colors.HEADER_TEXT, bg=Colors.BACKGROUND)
        header.pack(pady=(5, 10), padx=10, anchor="w")

        self.log_area = scrolledtext.ScrolledText(
            main_frame, wrap=tk.WORD, font=("Consolas", 11), bg=Colors.BACKGROUND,
            fg=Colors.INFO_TEXT, borderwidth=0, highlightthickness=0,
            insertbackground="white", padx=10
        )
        self.log_area.pack(expand=True, fill="both", padx=10, pady=5)
        self.log_area.config(state=tk.DISABLED)

        self.log_area.tag_config('user', foreground=Colors.USER_TEXT, font=("Segoe UI", 11, "bold"))
        self.log_area.tag_config('assistant', foreground=Colors.ASSISTANT_TEXT)
        self.log_area.tag_config('info', foreground=Colors.INFO_TEXT, font=("Segoe UI", 10, "italic"))
        self.log_area.tag_config('code', foreground="#89b4fa", font=("Consolas", 11))

        status_frame = tk.Frame(main_frame, bg=Colors.BACKGROUND)
        status_frame.pack(fill="x", padx=10, pady=(5, 5))

        self.voice_canvas = tk.Canvas(status_frame, width=40, height=20, bg=Colors.BACKGROUND, highlightthickness=0)
        self.voice_canvas.pack(side="left", padx=(0, 10))
        self.status_label = tk.Label(status_frame, text="Initializing...", font=("Segoe UI", 10), fg=Colors.INFO_TEXT, bg=Colors.BACKGROUND, anchor="w")
        self.status_label.pack(side="left")

        input_frame = tk.Frame(main_frame, bg=Colors.BACKGROUND)
        input_frame.pack(fill="x", padx=10, pady=(0, 10))
        self.user_input_entry = tk.Entry(input_frame, font=("Segoe UI", 11), bg=Colors.INPUT_BG, fg="white", relief="flat", insertbackground="white")
        self.user_input_entry.pack(fill="x", ipady=6)
        self.user_input_entry.bind("<Return>", self._on_enter_pressed)
        
        self._draw_voice_bars(silent=True)

    def _draw_voice_bars(self, silent=False):
        self.voice_canvas.delete("all")
        bar_width = 4
        bar_spacing = 2
        num_bars = 5
        max_height = 18

        for i in range(num_bars):
            x0 = i * (bar_width + bar_spacing)
            x1 = x0 + bar_width
            if silent:
                height = 2
                color = Colors.VOICE_BAR_SILENT
            else:
                height = random.randint(3, max_height)
                color = Colors.VOICE_BAR_ACTIVE
            y0 = (max_height - height) / 2 + 1
            y1 = y0 + height
            self.voice_canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

    def _animate_voice(self):
        if self.is_animating:
            self._draw_voice_bars(silent=False)
            self.root.after(60, self._animate_voice)
        else:
            self._draw_voice_bars(silent=True)

    def start_speaking_animation(self):
        if not self.is_animating:
            self.is_animating = True
            self._animate_voice()

    def stop_speaking_animation(self):
        self.is_animating = False

    def _on_enter_pressed(self, event=None):
        user_text = self.user_input_entry.get().strip()
        if user_text:
            self.user_input_queue.put(user_text)
            self.user_input_entry.delete(0, tk.END)

    def add_log(self, message: str, tag: str = 'info'):
        self.log_area.config(state=tk.NORMAL)
        prefix = ""
        if tag == 'user': prefix = "👤 You: "
        elif tag == 'assistant': prefix = "🤖 Assistant: "
        elif tag == 'info': prefix = "ℹ️ Info: "
        
        self.log_area.insert(tk.END, prefix + message + "\n\n", tag)
        self.log_area.config(state=tk.DISABLED)
        self.log_area.see(tk.END)

    def update_status(self, text: str):
        self.status_label.config(text=text)

    def get_user_text_input(self):
        try:
            return self.user_input_queue.get_nowait()
        except queue.Empty:
            return None

    def start(self):
        self.root.mainloop()