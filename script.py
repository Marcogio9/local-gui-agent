
#%%

import base64
import io
import json
import time
import pyautogui
from openai import OpenAI
from PIL import Image
from logger import LiveDecisionLogger
import re
from hud import AgentHUD

hud = AgentHUD()

# Configurazione endpoint locale (es. llama-server o LM Studio)
client = OpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")

SYSTEM_PROMPT = """Sei un agente che controlla un computer tramite mouse e tastiera.
Ricevi uno screenshot corrente dello schermo, l'obiettivo e lo storico delle tue azioni precedenti.

RISPONDI ESCLUSIVAMENTE con un oggetto JSON valido nel seguente formato:
{
  "reflection": "Confronta lo screenshot attuale con cosa ti aspettavi dallo step precedente. L'azione ha avuto successo o l'interfaccia è bloccata/in uno stato inatteso? Perché?",
  "thought": "Ragionamento su cosa fare ORA alla luce della riflessione. Se l'azione precedente è fallita, NON ripetere lo stesso identico input: prova un'alternativa (es. doppio click invece di singolo, premere Invio/Esc, cliccare sull'icona invece che sul testo).",
  "expected_outcome": "Cosa ti aspetti visivamente che cambi sullo schermo subito dopo l'azione che stai per fare?",
  "action": "click" | "right_click" | "double_click" | "write" | "press" | "finish",
  "point": [x, y],  // Coordinate normalizzate [0, 1000]
  "text": "stringa" // Testo o tasto opzionale
}
"""

time.sleep(5)

def record(self, step: int, thought: str, action: str, point: list | None, text: str | None, reflection: str = "", expected_outcome: str = ""):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = (
            f"--- STEP {step} [{timestamp}] ---\n"
            f"RIFLESSIONE: {reflection}\n"
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

def get_screenshot_b64() -> tuple[str, int, int]:
    screenshot = pyautogui.screenshot()
    width, height = screenshot.size
    
    # Conversione in base64 per l'invio all'API
    buffer = io.BytesIO()
    screenshot.save(buffer, format="JPEG", quality=80)
    b64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return b64_image, width, height

def execute_action(action_data: dict, screen_w: int, screen_h: int) -> bool:
    action = action_data.get("action")
    point = action_data.get("point")
    text = action_data.get("text")
    
    # 1. Mappatura coordinate da [0, 1000] a pixel effettivi
    if point:
        norm_x, norm_y = point
        target_x = int((norm_x / 1000.0) * screen_w)
        target_y = int((norm_y / 1000.0) * screen_h)
        pyautogui.moveTo(target_x, target_y, duration=0.15)

    # 2. Esecuzione comando
    if action == "click":
        pyautogui.click()
    elif action == "right_click":
        pyautogui.click(button='right')
    elif action == "double_click":
        pyautogui.doubleClick()
    elif action == "write" and text:
        pyautogui.write(text, interval=0.03)
    elif action == "press" and text:
        pyautogui.press(text)
    elif action == "finish":
        print("[Agente] Obiettivo completato.")
        return True
    
    return False

def run_agent_loop(goal: str, max_steps: int = 15):
    logger = LiveDecisionLogger("agent_thoughts.log")
    print(f"Avvio agente per l'obiettivo: '{goal}'")

    current_stream_buffer = ""
    conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Memorizza cosa il modello si aspettava dallo step precedente
    last_action_desc = "Nessuna azione precedente (primo step)."
    last_expected_outcome = "Schermata iniziale."

    try:
        for step in range(1, max_steps + 1):
            print(f"\n=== Step {step}/{max_steps} ===")
            current_stream_buffer = ""

            # 1. Screenshot corrente
            b64_img, screen_w, screen_h = get_screenshot_b64()

            # 2. Prompt contestuale: mette a confronto aspettativa passata e stato attuale
            user_instruction = f"""Obiettivo finale: {goal}

CONFRONTO STEP PRECEDENTE:
- Ultima azione tentata: {last_action_desc}
- Risultato visivo atteso: {last_expected_outcome}

Osserva attentamente l'immagine corrente:
1. L'aspettativa si è verificata? Se no, l'elemento è entrato in modalità rinomina, è apparso un errore o l'input non è stato registrato?
2. Se non ha funzionato, NON ripetere la stessa identica azione: cambia coordinate, premi un tasto di reset (es. 'esc' o 'enter') o usa un altro approccio."""

            current_user_message = {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_instruction},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}
                    }
                ]
            }

            messages_to_send = conversation_history + [current_user_message]

            # 3. Chiamata in streaming
            stream_response = client.chat.completions.create(
                model="Qwen3.5-4B",
                messages=messages_to_send,
                temperature=0.1,
                stream=True
            )

            # 4. Lettura streaming
            print("[Modello]: ", end="", flush=True)
            for chunk in stream_response:
                delta_obj = chunk.choices[0].delta
                reasoning_chunk = getattr(delta_obj, "reasoning_content", None) or ""
                content_chunk = delta_obj.content or ""
                token_text = reasoning_chunk if reasoning_chunk else content_chunk

                if token_text:
                    current_stream_buffer += token_text
                    if "hud" in globals() and hud:
                        hud.update_thought(current_stream_buffer)
                    print(token_text, end="", flush=True)
            print()

            # 5. Parsing JSON
            try:
                match = re.search(r"(\{.*\})", current_stream_buffer, re.DOTALL)
                if not match:
                    raise ValueError("Nessun JSON individuato nella risposta")

                clean_json_str = match.group(1)
                command = json.loads(clean_json_str)

            except (json.JSONDecodeError, ValueError) as err:
                print(f"\n[Errore] Parsing fallito: {err}")
                logger.record(
                    step=step,
                    thought="ERRORE: JSON non valido",
                    action="error",
                    point=None,
                    text=current_stream_buffer
                )
                continue

            reflection = command.get("reflection", "Nessuna riflessione")
            thought = command.get("thought", "")
            expected_outcome = command.get("expected_outcome", "Nessuna aspettativa specificata")
            action = command.get("action", "")
            point = command.get("point")
            text = command.get("text")

            # 6. Registrazione sul file di log
            logger.record(
                step=step,
                thought=thought,
                action=action,
                point=point,
                text=text,
                reflection=reflection,
                expected_outcome=expected_outcome
            )

            # 7. Aggiornamento aspettative per il prossimo ciclo
            last_action_desc = f"{action} su {point} (testo: '{text}')"
            last_expected_outcome = expected_outcome

            # 8. Aggiornamento cronologia testuale
            conversation_history.append({
                "role": "user",
                "content": f"[Step {step}] Azione tentata: {last_action_desc}. Aspettativa: {last_expected_outcome}"
            })
            conversation_history.append({
                "role": "assistant",
                "content": f"Riflessione: {reflection} | Prossima azione: {action}"
            })

            # Mantieni solo gli ultimi 4 turni per non appesantire la finestra
            if len(conversation_history) > 9:
                conversation_history = [conversation_history[0]] + conversation_history[-8:]

            # 9. Esecuzione sul computer
            is_finished = execute_action(command, screen_w, screen_h)
            if is_finished:
                logger.close("Completato con successo")
                break

            time.sleep(1.2)  # Pausa per dare tempo all'OS di mostrare la nuova finestra
        else:
            logger.close("Raggiunto il numero massimo di step")

    except KeyboardInterrupt:
        print("\n\n[!] Interruzione manuale da utente (Ctrl+C).")
        if current_stream_buffer:
            logger.record(
                step=step if 'step' in locals() else 0,
                thought=f"[GENERAZIONE INTERROTTA]\n{current_stream_buffer}",
                action="aborted",
                point=None,
                text=None
            )
        logger.close("Interruzione manuale Ctrl+C")

    except pyautogui.FailSafeException:
        print("\n[!] Interruzione Failsafe.")
        logger.close("Failsafe attivato")

    except Exception as e:
        print(f"\n[!] Errore imprevisto: {e}")
        logger.close(f"Eccezione: {e}")
        raise e

if __name__ == "__main__":
    # Failsafe: spostare violentemente il mouse nell'angolo in alto a sinistra interrompe pyautogui
    pyautogui.FAILSAFE = True
    
    goal = """crea un file di testo sul desktop e scrivi 'ciao', poi salva il file. Non usare scorciatoie da tastiera."""
    run_agent_loop(goal)