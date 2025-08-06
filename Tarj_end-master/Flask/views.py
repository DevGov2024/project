from main import app
from flask import render_template, request, send_file, redirect, url_for, session
import re
import tempfile
import os
import fitz  #
from docx import Document
import io
from historico_utils import salvar_envio
import uuid
import base64
from docx.shared import RGBColor

from PIL import Image, ImageDraw


# Habilita sessão para guardar dados temporários
app.secret_key = "segredo-muito-seguro"


PADROES_SENSIVEIS = {
    "CPF": r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b',
    "RG": r'\b\d{1,2}\.?\d{3}\.?\d{3}-?\d{1}\b',
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



@app.route("/",  methods=["GET", "POST"])
def homepage():
    
     return render_template("index.html")
    

def copiar_e_tarjar(original_doc, padroes):
    novo_doc = Document()

    for par in original_doc.paragraphs:
        texto = par.text
        for nome, regex in padroes.items():
            texto = re.sub(regex, lambda m: "█" * len(m.group()), texto)

        novo_doc.add_paragraph(texto)

    return novo_doc

# Padrões para DOCX

@app.route('/tarjar_docx', methods=['GET', 'POST'])
def tarjar_docx_preview():
    if request.method == 'POST':
        arquivo = request.files.get("docxfile")
        selecionados = request.form.getlist("itens")

        if not arquivo or not arquivo.filename.endswith('.docx'):
            return "Arquivo inválido. Envie um .docx.", 400

        padroes_ativos = {k: v for k, v in PADROES_SENSIVEIS.items() if k in selecionados}

        conteudo_bytes = arquivo.read()
        file_stream = io.BytesIO(conteudo_bytes)
        doc = Document(file_stream)

        ocorrencias = []
        for i, par in enumerate(doc.paragraphs):
            texto = par.text
            for tipo, regex in padroes_ativos.items():
                for m in re.finditer(regex, texto):
                    ocorrencias.append({
                        "tipo": tipo,
                        "texto": m.group(),
                        "paragrafo": i,
                        "start": m.start(),
                        "end": m.end(),
                        "id": f"{i}_{m.start()}_{m.end()}"
                    })

        temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".docx").name
        with open(temp_path, "wb") as f:
            f.write(conteudo_bytes)

        session['doc_ocorrencias'] = ocorrencias
        session['doc_path'] = temp_path

        return render_template("preview_docx.html", ocorrencias=ocorrencias, paragrafos=[p.text for p in doc.paragraphs])

    return render_template("tarjar_docx.html", padroes=PADROES_SENSIVEIS.keys())


@app.route("/aplicar_tarjas_docx", methods=["POST"])
def aplicar_tarjas_docx():
    selecionados = request.form.getlist("selecionados")
    trechos_manuais_raw = request.form.get("tarjas_manualmente_adicionadas", "")
    trechos_manuais = [t.strip() for t in trechos_manuais_raw.split("|") if t.strip()]

    ocorrencias = session.get("doc_ocorrencias", [])
    caminho = session.get("doc_path", None)

    if not caminho or not os.path.exists(caminho):
        return "Erro: Arquivo temporário não encontrado.", 400

    doc = Document(caminho)

    # Cria mapa de parágrafos para aplicar substituições
    paragrafo_edits = {}

    # Primeiro, aplica as substituições dos checkboxes
    for item in ocorrencias:
        if item["id"] in selecionados:
            idx = item["paragrafo"]
            texto_original = doc.paragraphs[idx].text
            if idx not in paragrafo_edits:
                paragrafo_edits[idx] = texto_original

            start, end = item["start"], item["end"]
            trecho = texto_original[start:end]
            texto_editado = paragrafo_edits[idx].replace(trecho, "█" * len(trecho), 1)
            paragrafo_edits[idx] = texto_editado

    # Agora aplica os trechos manuais
    if trechos_manuais:
        for i, par in enumerate(doc.paragraphs):
            texto = paragrafo_edits.get(i, par.text)
            for trecho_manual in trechos_manuais:
                if trecho_manual in texto:
                    texto = texto.replace(trecho_manual, "█" * len(trecho_manual))
                    paragrafo_edits[i] = texto

    # Atualiza os parágrafos editados
    for i, novo_texto in paragrafo_edits.items():
        par = doc.paragraphs[i]
        par.clear()
        run = par.add_run(novo_texto)
        run.font.color.rgb = RGBColor(0, 0, 0)

    # Salva em memória
    mem_file = io.BytesIO()
    doc.save(mem_file)
    mem_file.seek(0)
    os.remove(caminho)

    return send_file(
        mem_file,
        as_attachment=True,
        download_name="documento_tarjado.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


@app.route('/tarjar_pdf', methods=['GET', 'POST'])
def tarjar_pdf():
    if request.method == 'POST':
        arquivo = request.files.get('pdffile')
        tipos_selecionados = request.form.getlist('tipos')  

        if not arquivo or not arquivo.filename.endswith('.pdf'):
            return "Arquivo inválido. Envie um .pdf.", 400

        padroes_filtrados = {k: v for k, v in PADROES_SENSIVEIS.items() if k in tipos_selecionados}

        pdf_bytes = arquivo.read()
        doc = fitz.open("pdf", pdf_bytes)

        ocorrencias = []
        redactions_por_pagina = {}

        for pagina_num in range(len(doc)):
            pagina = doc[pagina_num]
            texto = pagina.get_text("text")

            for tipo, regex in padroes_filtrados.items():
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

        # Aplicar redactions (apenas para visualização)
        for pagina_idx, areas in redactions_por_pagina.items():
            pagina = doc[pagina_idx]
            for area in areas:
                pagina.add_redact_annot(area, fill=(0, 0, 0))
            pagina.apply_redactions()

        # Salvar o PDF modificado em memória
        mem_file = io.BytesIO()
        doc.save(mem_file)
        mem_file.seek(0)
        doc.close()

        pdf_b64 = base64.b64encode(mem_file.read()).decode('utf-8')

        # Ainda salvamos o original temporariamente, caso o usuário queira aplicar tarjas reais depois
        temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
        with open(temp_path, 'wb') as f:
            f.write(pdf_bytes)

        session['pdf_path'] = temp_path
        session['pdf_ocorrencias'] = ocorrencias

        return render_template("preview_pdf.html", ocorrencias=ocorrencias, pdf_data=pdf_b64)

    return render_template('tarjar_pdf.html', padroes=PADROES_SENSIVEIS.keys())
    

@app.route('/aplicar_tarjas_pdf', methods=['POST'])
def aplicar_tarjas_pdf():

    selecionados = request.form.getlist('selecionados')
    trechos_manuais_raw = request.form.get('tarjas_manualmente_adicionadas', '')
    trechos_manuais = [t.strip() for t in trechos_manuais_raw.split('|') if t.strip()]

    caminho = session.get('pdf_path')
    ocorrencias = session.get('pdf_ocorrencias', [])

    if not caminho or not os.path.exists(caminho):
        return "Erro: Muitos dados para processar. Tente com menos dados para tarjar", 400

    doc = fitz.open(caminho)

    redactions_por_pagina = {}

    # Redações automáticas
    for item in ocorrencias:
        if item['id'] in selecionados:
            pagina_idx = item['pagina']
            termo = item['texto']
            pagina = doc[pagina_idx]

            # Busca por áreas correspondentes ao termo
            areas = pagina.search_for(termo)
            for area in areas:
                # Verifica se essa página já tem lista de redactions
                redactions_por_pagina.setdefault(pagina_idx, []).append(area)

    # Redações manuais
    if trechos_manuais:
        for num_pagina in range(len(doc)):
            pagina = doc[num_pagina]
            texto_pagina = pagina.get_text()
            for trecho in trechos_manuais:
                if trecho in texto_pagina:
                    areas = pagina.search_for(trecho)
                    for area in areas:
                        redactions_por_pagina.setdefault(num_pagina, []).append(area)

    # Aplicar redactions por página (depois de acumular todos)
    for pagina_idx, areas in redactions_por_pagina.items():
        pagina = doc[pagina_idx]
        for area in areas:
            pagina.add_redact_annot(area, fill=(0, 0, 0))
        pagina.apply_redactions()  # Só uma vez por página!

    # Salvar PDF final
    mem_file = io.BytesIO()
    doc.save(mem_file)
    mem_file.seek(0)
    doc.close()
    os.remove(caminho)

    return send_file(
        mem_file,
        as_attachment=True,
        download_name="documento_tarjado.pdf",
        mimetype="application/pdf"
    )

@app.route('/preview_pdf', methods=['POST'])
def preview_pdf():
    arquivo = request.files['arquivo']
    nome_temporario = os.path.join('uploads', f"{uuid.uuid4()}.pdf")
    arquivo.save(nome_temporario)

    doc = fitz.open(nome_temporario)

    pdf_data = base64.b64encode(open(nome_temporario, "rb").read()).decode('utf-8')

    ocorrencias = detectar_dados(doc)  # sua função atual
    texto_extraido = ""
    for pagina in doc:
        texto_extraido += pagina.get_text() + "\n"

    doc.close()

    session['pdf_path'] = nome_temporario
    session['pdf_ocorrencias'] = ocorrencias

    return render_template(
        "preview_pdf.html",
        pdf_data=pdf_data,
        ocorrencias=ocorrencias,
        texto_extraido=texto_extraido
    )

@app.route('/download_pdf_tarjado')
def download_pdf_tarjado():
    path = session.get('pdf_tarjado_path', None)
    if not path or not os.path.exists(path):
        return "Nenhum PDF tarjado disponível.", 400

    return send_file(path, as_attachment=True, download_name="documento_tarjado.pdf", mimetype="application/pdf")
