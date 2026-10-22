import tkinter as tk
import threading

class AgentHUD:
    def __init__(self):
        self.root = None
        self.label = None
        self._ready = threading.Event()
        self.thread = threading.Thread(target=self._run_gui, daemon=True)
        self.thread.start()
        self._ready.wait()

    def _run_gui(self):
        self.root = tk.Tk()
        self.root.title("Agent Live HUD")
        self.root.geometry("450x120+20+20")  # Dimensioni e posizione (in alto a sinistra)
        self.root.attributes("-topmost", True)  # Sempre sopra le altre finestre
        self.root.attributes("-alpha", 0.85)    # Trasparenza per non coprire del tutto
        self.root.configure(bg="#1e1e1e")

        self.label = tk.Label(
            self.root, 
            text="In attesa dell'agente...", 
            fg="#00ff66", 
            bg="#1e1e1e", 
            font=("Consolas", 10),
            justify="left",
            wraplength=430,
            anchor="nw"
        )
        self.label.pack(fill="both", expand=True, padx=8, pady=8)
        self._ready.set()
        self.root.mainloop()

    def update_thought(self, text: str):
        if self.root and self.label:
            # Aggiorna il testo in modo thread-safe
            self.root.after(0, lambda: self.label.config(text=text[-250:]))