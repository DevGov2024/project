from flask import Flask
from flask_session import Session
import os

app = Flask(__name__)

# ---- CONFIGURAÇÃO DA SESSÃO ----
app.config['SECRET_KEY'] = 'minha-chave-secreta'  # troque por algo forte

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(BASE_DIR, 'flask_session_data')
os.makedirs(SESSION_DIR, exist_ok=True)

app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = SESSION_DIR
app.config['SESSION_PERMANENT'] = False

# Ativa Flask-Session
Session(app)
# --------------------------------

from views import *   # importa depois da configuração

if __name__ == "__main__":
    app.run(debug=True)
