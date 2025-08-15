import io
import os
import re
import base64
import tempfile
import fitz  # PyMuPDF

def gerar_preview_pdf(pdf_bytes, padroes_ativos):
    doc = fitz.open("pdf", pdf_bytes)
    ocorrencias = []
    redactions_por_pagina = {}

    for pagina_num in range(len(doc)):
        pagina = doc[pagina_num]
        texto = pagina.get_text("text")

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

    # Aplicar redactions para visualização
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

    # Salvar temporário para futuras edições
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
