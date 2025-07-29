import os
import json
from datetime import datetime

LOG_PATH = "logs/historico_envios.json"

def salvar_envio(nome_arquivo, tipo):
    os.makedirs("logs", exist_ok=True)

    historico = []
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            historico = json.load(f)

    historico.append({
        "nome": nome_arquivo,
        "tipo": tipo,
        "data": datetime.now().strftime("%d/%m/%Y %H:%M")
    })

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(historico, f, indent=2, ensure_ascii=False)

def carregar_historico():
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
