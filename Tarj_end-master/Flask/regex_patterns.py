# regex_patterns.py
import re

# Usamos um dicionário de strings para criar os padrões compilados
# Isso mantém a legibilidade
raw_patterns = {
    "CPF": r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b',
    "RG": r'\b(?:\d{2}\.\d{3}\.\d{3}-[\dXx]|\d{1,2}\.\d{3}\.\d{3}(?![\d-]))\b',
    "EMAIL": r'\b[\w\.-]+@[\w\.-]+\.\w{2,}\b',
    "TELEFONE": r'\(?\d{2}\)?\s?\d{4,5}-\d{4}',
    "CEP": r'\b(?:\d{5}|\d{2}\.?\d{3})-\d{3}\b',
    "CNPJ": r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b',
    "CARTAO": r'(?:\d[ -]*?){13,16}',
    "PLACA": r'\b[A-Z]{3}-?\d{1}[A-Z0-9]{1}\d{2}\b',
    "DATA": r'\b\d{2}/\d{2}/\d{4}\b',
    "ENDERECO": r"\b(?:Rua|Av|Avenida|Travessa|Estrada|Rodovia|R\.|Av\.?)\.?\s+[A-Za-zÀ-ÖØ-öø-ÿ0-9\s]+,\s*\d+",
    "NOME": r'\b([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ][a-záéíóúâêîôûãõç]+(?:\s+(?:da|de|do|dos|das|e)?\s*[A-Z][a-z]+)+)\b',
}

# Agora, criamos o dicionário final com os padrões compilados
# O seu código principal vai usar este dicionário
PADROES_SENSIVEIS = {key: re.compile(pattern) for key, pattern in raw_patterns.items()}