import threading
import tkinter as tk


class AgentHUD:

    def __init__(self):
        self.root = None
        self.text_widget = None
        self._ready = threading.Event()
        self.thread = threading.Thread(target=self._run_gui, daemon=True)
        self.thread.start()
        self._ready.wait()

    def _run_gui(self):
        self.root = tk.Tk()
        self.root.title("Agent Live HUD")
        self.root.geometry("500x160+20+20")  # Dimensioni della finestrella
        self.root.attributes(
            "-topmost", True
        )  # Finestra sempre in primo piano
        self.root.attributes("-alpha", 0.88)  # Trasparenza ottimale[cite: 5]
        self.root.configure(bg="#1e1e1e")  #[cite: 5]

        # Widget Text invece di Label per supportare lo scrolling naturale
        self.text_widget = tk.Text(
            self.root,
            bg="#1e1e1e",
            fg="#00ff66",
            font=("Consolas", 10),
            wrap="word",  # Manda a capo le parole intere, senza spezzare i caratteri
            bd=0,
            padx=10,
            pady=10,
            highlightthickness=0,
        )
        self.text_widget.pack(fill="both", expand=True)

        self.text_widget.insert(tk.END, "In attesa dell'agente...\n")
        self.text_widget.config(
            state="disabled"
        )  # Rende il testo non modificabile dall'utente

        self._ready.set()
        self.root.mainloop()

    def update_thought(self, text: str):
        if self.root and self.text_widget:
            # Aggiornamento thread-safe nel loop principale di Tkinter[cite: 5]
            self.root.after(0, self._append_or_refresh, text)

    def _append_or_refresh(self, full_text: str):
        self.text_widget.config(state="normal")
        self.text_widget.delete("1.0", tk.END)

        # Manteniamo le ultime 10 righe per non appesantire la finestra
        lines = full_text.splitlines(keepends=True)
        recent_text = "".join(lines[-10:]) if len(lines) > 10 else full_text

        self.text_widget.insert(tk.END, recent_text)
        # Scroll automatico verso l'ultima riga visibile
        self.text_widget.see(tk.END)
        self.text_widget.config(state="disabled")