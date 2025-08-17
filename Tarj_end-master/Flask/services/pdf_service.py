import io
import os
import re
import base64
import tempfile
import fitz  # PyMuPDF
from PIL import Image
import pytesseract

import spacy

# Carregar modelo do spaCy
nlp = spacy.load("pt_core_news_sm")

def detectar_com_spacy(texto):
    """
    Retorna entidades reconhecidas pelo spaCy no texto.
    """
    doc = nlp(texto)
    entidades = []
    for ent in doc.ents:
        entidades.append({
            "texto": ent.text,
            "label": ent.label_,  # PERSON, ORG, GPE...
        })
    return entidades

def gerar_redactions(doc, ocorrencias, selecionados=None, trechos_manuais=None, preservar_logo=False):
    redactions_por_pagina = {}

    # Tarjas automáticas
    if selecionados:
        for item in ocorrencias:
            if item.get('id') in selecionados:
                pagina_idx = item['pagina']
                termo = item['texto']
                pagina = doc[pagina_idx]
                areas = pagina.search_for(termo)
                for area in areas:
                    if preservar_logo and area.y0 < 100:
                        continue
                    redactions_por_pagina.setdefault(pagina_idx, []).append(area)

    # Tarjas manuais
    if trechos_manuais:
        for num_pagina in range(len(doc)):
            pagina = doc[num_pagina]
            texto_pagina = pagina.get_text()
            for trecho in trechos_manuais:
                if trecho in texto_pagina:
                    areas = pagina.search_for(trecho)
                    for area in areas:
                        if preservar_logo and area.y0 < 100:
                            continue
                        redactions_por_pagina.setdefault(num_pagina, []).append(area)

    return redactions_por_pagina

def extrair_texto_pdf(pagina, usar_ocr=False):
    """
    Retorna o texto de uma página. Usa OCR se necessário.
    """
    texto = pagina.get_text("text")

    if usar_ocr or not texto.strip():
        # Renderiza a página como imagem para OCR
        pix = pagina.get_pixmap()
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        texto = pytesseract.image_to_string(img, lang='por')

    # Normaliza espaços e quebras de linha
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

def gerar_preview_pdf(pdf_bytes, padroes_ativos, usar_spacy=False):
    doc = fitz.open("pdf", pdf_bytes)
    ocorrencias = []
    redactions_por_pagina = {}

    for pagina_num in range(len(doc)):
        pagina = doc[pagina_num]
        texto = pagina.get_text("text")

        # --- Regex padrão ---
        for tipo, regex in padroes_ativos.items():
            for m in re.finditer(regex, texto):
                termo = m.group()
                ocorrencias.append({
                    "id": f"{pagina_num}_{m.start()}_{m.end()}",
                    "tipo": tipo,
                    "texto": termo,
                    "pagina": pagina_num,
                    "start": m.start(),
                    "end": m.end()
                })
                areas = pagina.search_for(termo)
                for area in areas:
                    redactions_por_pagina.setdefault(pagina_num, []).append(area)

        # --- spaCy avançado ---
        if usar_spacy:
            entidades = detectar_com_spacy(texto)
            for ent in entidades:
                termo = ent["texto"]
                ocorrencias.append({
                    "id": f"{pagina_num}_{hash(termo)}",
                    "tipo": f"NER_{ent['label']}",
                    "texto": termo,
                    "pagina": pagina_num
                })
                areas = pagina.search_for(termo)
                for area in areas:
                    redactions_por_pagina.setdefault(pagina_num, []).append(area)

    # Aplicar redactions para preview
    for pagina_idx, areas in redactions_por_pagina.items():
        pagina = doc[pagina_idx]
        for area in areas:
            pagina.add_redact_annot(area, fill=(0,0,0))
        pagina.apply_redactions()

    mem_file = io.BytesIO()
    doc.save(mem_file)
    mem_file.seek(0)
    doc.close()

    pdf_b64 = base64.b64encode(mem_file.read()).decode('utf-8')

    temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
    with open(temp_path, 'wb') as f:
        f.write(pdf_bytes)

    return ocorrencias, pdf_b64, temp_path


def aplicar_tarjas_pdf(caminho, ocorrencias, selecionados, trechos_manuais, preservar_logo=False):
    doc = fitz.open(caminho)
    redactions_por_pagina = {}

    # Tarjas automáticas
    for item in ocorrencias:
        if item['id'] in selecionados:
            pagina_idx = item['pagina']
            termo = item['texto']
            pagina = doc[pagina_idx]
            areas = pagina.search_for(termo)
            for area in areas:
                if preservar_logo and area.y0 < 100:
                    continue
                redactions_por_pagina.setdefault(pagina_idx, []).append(area)

    # Tarjas manuais
    if trechos_manuais:
        for num_pagina in range(len(doc)):
            pagina = doc[num_pagina]
            texto_pagina = pagina.get_text()
            for trecho in trechos_manuais:
                if trecho in texto_pagina:
                    areas = pagina.search_for(trecho)
                    for area in areas:
                        if preservar_logo and area.y0 < 100:
                            continue
                        redactions_por_pagina.setdefault(num_pagina, []).append(area)

    # Aplica redactions
    for pagina_idx, areas in redactions_por_pagina.items():
        pagina = doc[pagina_idx]
        for area in areas:
            pagina.add_redact_annot(area, fill=(0,0,0))
        pagina.apply_redactions()

    mem_file = io.BytesIO()
    doc.save(mem_file)
    mem_file.seek(0)
    doc.close()
    return mem_file


def atualizar_preview_pdf(caminho, ocorrencias, selecionados, trechos_manuais):
    doc = fitz.open(caminho)
    redactions_por_pagina = {}

    # Tarjas automáticas
    for item in ocorrencias:
        if item['id'] in selecionados:
            pagina_idx = item['pagina']
            termo = item['texto']
            pagina = doc[pagina_idx]
            areas = pagina.search_for(termo)
            for area in areas:
                redactions_por_pagina.setdefault(pagina_idx, []).append(area)

    # Tarjas manuais
    for num_pagina in range(len(doc)):
        pagina = doc[num_pagina]
        texto_pagina = pagina.get_text()
        for trecho in trechos_manuais:
            if trecho in texto_pagina:
                areas = pagina.search_for(trecho)
                for area in areas:
                    redactions_por_pagina.setdefault(num_pagina, []).append(area)

    # Aplica redactions para visualização
    for pagina_idx, areas in redactions_por_pagina.items():
        pagina = doc[pagina_idx]
        for area in areas:
            pagina.add_redact_annot(area, fill=(0,0,0))
        pagina.apply_redactions()

    mem_file = io.BytesIO()
    doc.save(mem_file)
    mem_file.seek(0)
    doc.close()

    pdf_b64 = base64.b64encode(mem_file.read()).decode('utf-8')
    return pdf_b64
