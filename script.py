#%%

import base64
import io
import json
import re
import time
from hud import AgentHUD
from logger import LiveDecisionLogger
from openai import OpenAI
import pyautogui

hud = AgentHUD()

time.sleep(5)

client = OpenAI(base_url="http://localhost:8080/v1", api_key="not-needed")

SYSTEM_PROMPT = """Sei un agente GUI autonomo che controlla un computer tramite mouse e tastiera.
Ricevi uno screenshot corrente, l'obiettivo, l'azione precedente e il risultato che ti aspettavi.

PRINCIPIO FONDAMENTALE DI AUTO-CORREZIONE:
Non dare mai per scontato che la tua azione abbia funzionato. Guarda lo screenshot corrente:
- Se l'interfaccia NON è nello stato atteso o sembra identica a prima, NON ripetere la stessa identica azione.
- Chiediti PERCHÉ ha fallito: le coordinate erano leggermente spostate? Il menu si è chiuso o non si è aperto? C'era bisogno di un doppio click o del tasto Enter?
- Definisci la correzione pratica prima di agire.
- Non fare assunzioni: basati unicamente su ciò che vedi a video.

RISPONDI ESCLUSIVAMENTE con un JSON valido con questa struttura:
{
  "actual_state": "Descrizione obiettiva di cosa vedi ORA sullo schermo (finestre aperte, menu visibili, stato del cursore).",
  "verification": "L'aspettativa dello step precedente si è avverata? (SÌ / NO / PARZIALMENTE). Spiega cosa è andato storto se NO.",
  "correzione_necessaria": "Se l'azione prima ha fallito o è imprecisa, descrivi la correzione fisica concreta (es. 'fare doppio click un po' più su', 'cliccare 20px più a destra sull'icona', 'premere esc per sbloccare il menu'). Se ha avuto successo o è il primo step, scrivi tassativamente 'nessuna'.",
  "thought": "Ragionamento per il prossimo passo applicando la correzione necessaria.",
  "expected_outcome": "Cosa DEVE cambiare visivamente sullo schermo subito dopo l'azione che stai per compiere.",
  "action": "click" | "right_click" | "double_click" | "write" | "press" | "finish",
  "point": [x, y],  // Solo per click/double_click/right_click (coordinate normalizzate [0, 1000])
  "text": "stringa" // Solo per write/press
}
"""


def get_screenshot_b64() -> tuple[str, int, int]:
    screenshot = pyautogui.screenshot()
    width, height = screenshot.size

    buffer = io.BytesIO()
    screenshot.save(buffer, format="JPEG", quality=80)
    b64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return b64_image, width, height


def execute_action(action_data: dict, screen_w: int, screen_h: int) -> bool:
    action = action_data.get("action")
    point = action_data.get("point")
    text = action_data.get("text")

    # Mappatura coordinate normalizzate [0, 1000] in coordinate assolute dello schermo
    if point:
        norm_x, norm_y = point
        target_x = int((norm_x / 1000.0) * screen_w)
        target_y = int((norm_y / 1000.0) * screen_h)
        pyautogui.moveTo(target_x, target_y, duration=0.15)

    if action == "click":
        pyautogui.click()
    elif action == "right_click":
        pyautogui.click(button="right")
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

    last_action_desc = "Nessuna (Inizio sessione)"
    last_expected_outcome = "Desktop o finestra di lavoro pronta per iniziare."

    try:
        for step in range(1, max_steps + 1):
            print(f"\n=== Step {step}/{max_steps} ===")
            current_stream_buffer = ""

            b64_img, screen_w, screen_h = get_screenshot_b64()

            user_prompt = f"""OBIETTIVO: {goal}

VERIFICA DELLO STATO PRECEDENTE:
- Mossa appena tentata: {last_action_desc}
- Cosa ti aspettavi di vedere: "{last_expected_outcome}"

DOMANDE GUIDA PER IL JSON:
1. Guarda l'immagine: lo schermo rispecchia davvero la tua aspettativa o sei bloccato?
2. Se non ha funzionato, indica in 'correzione_necessaria' la micro-correzione esatta (es. cliccare più in alto, premere esc, ecc.) e applicala in 'thought' e 'action'."""

            current_user_message = {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_img}"
                        },
                    },
                ],
            }

            messages_to_send = conversation_history + [current_user_message]

            stream_response = client.chat.completions.create(
                model="Qwen3.5-4B",
                messages=messages_to_send,
                temperature=0.5,
                max_tokens=800,
                stream=True,
            )

            print("[Modello]: ", end="", flush=True)
            for chunk in stream_response:
                delta_obj = chunk.choices[0].delta
                reasoning_chunk = (
                    getattr(delta_obj, "reasoning_content", None) or ""
                )
                content_chunk = delta_obj.content or ""
                token_text = (
                    reasoning_chunk if reasoning_chunk else content_chunk
                )

                if token_text:
                    current_stream_buffer += token_text
                    if "hud" in globals() and hud:
                        hud.update_thought(current_stream_buffer)
                    print(token_text, end="", flush=True)
            print()

            try:
                match = re.search(r"(\{.*\})", current_stream_buffer, re.DOTALL)
                if not match:
                    raise ValueError("Nessun blocco JSON trovato")

                clean_json_str = match.group(1)
                command = json.loads(clean_json_str)

            except (json.JSONDecodeError, ValueError) as err:
                print(f"\n[Errore] Parsing fallito: {err}")
                logger.record(
                    step=step,
                    thought="ERRORE: Output non in formato JSON",
                    action="error",
                    point=None,
                    text=current_stream_buffer,
                )
                continue

            actual_state = command.get("actual_state", "")
            verification = command.get("verification", "")
            correzione = command.get("correzione_necessaria", "nessuna")
            thought = command.get("thought", "")
            expected_outcome = command.get(
                "expected_outcome", "Nessuna aspettativa"
            )
            action = command.get("action", "")
            point = command.get("point")
            text = command.get("text")

            # Registrazione nel logger arricchita
            logger.record(
                step=step,
                thought=f"[{verification}] {thought}",
                action=action,
                point=point,
                text=text,
                reflection=f"Stato: {actual_state} | Esito: {verification}",
                expected_outcome=expected_outcome,
                correzione_necessaria=correzione,
            )

            last_action_desc = (
                f"{action} su {point}"
                if point
                else f"{action} con testo '{text}'"
            )
            last_expected_outcome = expected_outcome

            # Aggiungiamo alla cronologia anche la correzione adottata per mantenere la coerenza
            conversation_history.append(
                {
                    "role": "user",
                    "content": f"[Step {step}] Azione eseguita: {last_action_desc}. Aspettativa: {last_expected_outcome}",
                }
            )
            conversation_history.append(
                {
                    "role": "assistant",
                    "content": f"Esito: {verification} | Correzione applicata: {correzione} | Nuova azione: {action} su {point or text}.",
                }
            )

            if len(conversation_history) > 7:
                conversation_history = [
                    conversation_history[0]
                ] + conversation_history[-6:]

            is_finished = execute_action(command, screen_w, screen_h)
            if is_finished:
                logger.close("Completato con successo")
                break

            time.sleep(1.2)
        else:
            logger.close("Raggiunto il numero massimo di step")

    except KeyboardInterrupt:
        print("\n\n[!] Interruzione manuale da utente (Ctrl+C).")
        logger.close("Interruzione manuale Ctrl+C")

    except pyautogui.FailSafeException:
        print("\n[!] Interruzione Failsafe.")
        logger.close("Failsafe attivato")

    except Exception as e:
        print(f"\n[!] Errore imprevisto: {e}")
        logger.close(f"Eccezione: {e}")
        raise e


if __name__ == "__main__":
    pyautogui.FAILSAFE = True
    goal = """crea un file di testo sul desktop e scrivi 'ciao', poi salva il file, infine chiudilo cliccando sulla 'x'. 
    Non usare scorciatoie da tastiera."""
    run_agent_loop(goal)