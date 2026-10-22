import json
import time
from datetime import datetime
from pathlib import Path


class LiveDecisionLogger:

    def __init__(self, log_path: str = "agent_thoughts.log"):
        self.file = open(log_path, "a", encoding="utf-8")
        self._write_separator("NUOVA SESSIONE AVVIATA")

    def _write_separator(self, title: str):
        border = "=" * 60
        header = f"\n{border}\n[{datetime.now().strftime('%H:%M:%S')}] {title}\n{border}\n"
        print(header, end="")
        self.file.write(header)
        self.file.flush()

    def record(
        self,
        step: int,
        thought: str,
        action: str,
        point: list | None,
        text: str | None,
        reflection: str = "",
        expected_outcome: str = "",
        correzione_necessaria: str = "nessuna",
    ):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = (
            f"--- STEP {step} [{timestamp}] ---\n"
            f"RIFLESSIONE: {reflection}\n"
            f"CORREZIONE:  {correzione_necessaria}\n"
            f"PENSIERO:    {thought}\n"
            f"ASPETTATIVA: {expected_outcome}\n"
            f"AZIONE:      {action}\n"
            f"TARGET:      {point}\n"
            f"TESTO:       {text}\n"
            f"{'-' * 40}\n"
        )

        print(entry, end="")
        self.file.write(entry)
        self.file.flush()

    def close(self, reason: str = "Terminato"):
        self._write_separator(f"SESSIONE INTERROTTA ({reason})")
        self.file.close()