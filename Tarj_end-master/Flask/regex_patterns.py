# regex_patterns.py
import re

# Usamos um dicionário de strings para criar os padrões compilados
# Isso mantém a legibilidade
raw_patterns = {
    "CPF": r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b',
    "RG": r"\b\d{1,2}\.?\d{3}\.?\d{3}-?[0-9Xx]\b",
    "EMAIL": r'\b[\w\.-]+@[\w\.-]+\.\w{2,}\b',
    "TELEFONE": r'\(?\d{2}\)?\s?\d{4,5}-\d{4}',
    "CEP": r'\b(?:\d{5}|\d{2}\.?\d{3})-\d{3}\b',
    "CNPJ": r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b',
    "CARTAO": r'(?:\d[ -]*?){13,16}',
    "PLACA": r'\b[A-Z]{3}-?\d{1}[A-Z0-9]{1}\d{2}\b',
    "DATA": r'\b\d{2}/\d{2}/\d{4}\b',
    "ENDERECO": r"\b(?:Rua|R\.|Avenida|Av\.|Alameda|Travessa|Tv\.|Estrada|Rodovia|Praça|Pça\.|Largo|Lg\.)"
                r"\s+[A-Za-zÀ-ÖØ-öø-ÿ0-9'ºª\.\- ]+"
                r",\s*\d+[A-Za-z]?"                                  # número (ex.: 123, 123A)
                r"(?:\s*(?:apto|apt|ap|bloco|bl|sala|sl|cj|conj|casa|fundos|km|lote|lt|quadra|qd|andar)\.?\s*[A-Za-z0-9\-ºª]+)?"  # complemento opcional
                r"(?:\s*-\s*[A-Za-zÀ-ÖØ-öø-ÿ' \.\-]+)?"              # bairro opcional após " - "
                ,
    "NOME": r"\b(?:[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ][a-záéíóúâêîôûãõç]+(?:-[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ][a-záéíóúâêîôûãõç]+)?)"      # 1º token
            r"(?:\s+(?:(?:da|das|de|do|dos|e)\s+)?"
            r"[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ][a-záéíóúâêîôûãõç]+(?:-[A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ][a-záéíóúâêîôûãõç]+)?){1,}\b",
}

# Agora, criamos o dicionário final com os padrões compilados
# O seu código principal vai usar este dicionário
PADROES_SENSIVEIS = {key: re.compile(pattern) for key, pattern in raw_patterns.items()}