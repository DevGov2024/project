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

padroes = {
    "CPF": r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
    "CNPJ": r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b",
    "Telefone": r"\b\(?\d{2}\)?\s?\d{4,5}-\d{4}\b",
    "E-mail": r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b",
    "Senha": r"\bsenha\s*[:=]?\s*\S+",
    "Processo CNJ": r"\b\d{7}-\d{2}\.\d{4}\.\d{1}\.\d{2}\.\d{4}\b",
    "CEP": r"\b\d{5}-\d{3}\b",
    "Cartão de Crédito": r"\b(?:\d[ -]*?){13,16}\b",
    "RG": r"\b\d{2}\.\d{3}\.\d{3}-\d{1}\b",
    "Passaporte": r"\b[A-Z]{1}\d{7}\b",
    "endereço" : r"(\d+)\s+([A-Za-z\s]+),\s*([A-Za-z\s]+)(?:,\s*(.*))?"
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
PADROES_SENSIVEIS = {
    "CPF": r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b',
    "RG": r'\b\d{1,2}\.?\d{3}\.?\d{3}-?\d{1}\b',
    "EMAIL": r'\b[\w\.-]+@[\w\.-]+\.\w{2,}\b',
    "TELEFONE": r'\(?\d{2}\)?\s?\d{4,5}-\d{4}',
    "CEP": r'\b\d{5}-\d{3}\b',
    "CNPJ": r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b',
    "CARTAO": r'(?:\d[ -]*?){13,16}',
    "PLACA": r'\b[A-Z]{3}-?\d{1}[A-Z0-9]{1}\d{2}\b',
    "DATA": r'\b\d{2}/\d{2}/\d{4}\b'
}

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
    ocorrencias = session.get("doc_ocorrencias", [])
    caminho = session.get("doc_path", None)

    if not caminho or not os.path.exists(caminho):
        return "Erro: Arquivo temporário não encontrado.", 400

    doc = Document(caminho)

    for item in ocorrencias:
        if item["id"] in selecionados:
            par_index = item["paragrafo"]
            par = doc.paragraphs[par_index]
            texto = par.text

            start, end = item["start"], item["end"]
            substituto = "█" * (end - start)

            # Reconstruir o parágrafo com substituição
            novo_texto = texto[:start] + substituto + texto[end:]
            par.clear()  # Remove o conteúdo atual

            # Adiciona novo run com formatação
            run = par.add_run(novo_texto)
            run.font.color.rgb = RGBColor(0, 0, 0)  # fonte preta

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

# Padrões para tarjamento
PADROES_SENSIVEIS_PDF = {
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


@app.route('/tarjar_pdf', methods=['GET', 'POST'])
def tarjar_pdf():
    if request.method == 'POST':
        arquivo = request.files.get('pdffile')

        if not arquivo or not arquivo.filename.endswith('.pdf'):
            return "Arquivo inválido. Envie um .pdf.", 400

        pdf_bytes = arquivo.read()
        doc = fitz.open("pdf", pdf_bytes)

        ocorrencias = []
        for pagina_num in range(len(doc)):
            pagina = doc[pagina_num]
            texto = pagina.get_text("text")
            for tipo, regex in PADROES_SENSIVEIS_PDF.items():
                for m in re.finditer(regex, texto):
                    ocorrencias.append({
                        "id": f"{pagina_num}_{m.start()}_{m.end()}",
                        "tipo": tipo,
                        "texto": m.group(),
                        "pagina": pagina_num,
                        "start": m.start(),
                        "end": m.end()
                    })

        # Salva caminho temporário para depois aplicar as tarjas
        temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
        with open(temp_path, 'wb') as f:
            f.write(pdf_bytes)

        session['pdf_path'] = temp_path
        session['pdf_ocorrencias'] = ocorrencias

        pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')

        return render_template("preview_pdf.html", ocorrencias=ocorrencias, pdf_data=pdf_b64)

    return render_template('tarjar_pdf.html', padroes=PADROES_SENSIVEIS_PDF.keys())
@app.route('/aplicar_tarjas_pdf', methods=['POST'])
def aplicar_tarjas_pdf():
    selecionados = request.form.getlist('selecionados')
    caminho = session.get('pdf_path')
    ocorrencias = session.get('pdf_ocorrencias', [])

    if not caminho or not os.path.exists(caminho):
        return "Erro: Arquivo temporário não encontrado.", 400

    doc = fitz.open(caminho)

    for item in ocorrencias:
        if item['id'] in selecionados:
            pagina = doc[item['pagina']]
            termo = item['texto']
            areas = pagina.search_for(termo)
            for area in areas:
                pagina.add_redact_annot(area, fill=(0, 0, 0))
            pagina.apply_redactions()

    mem_file = io.BytesIO()
    doc.save(mem_file)
    mem_file.seek(0)
    doc.close()

    # Remover arquivo temporário
    os.remove(caminho)

    return send_file(
        mem_file,
        as_attachment=True,
        download_name="documento_tarjado.pdf",
        mimetype="application/pdf"
    )


@app.route('/download_pdf_tarjado')
def download_pdf_tarjado():
    path = session.get('pdf_tarjado_path', None)
    if not path or not os.path.exists(path):
        return "Nenhum PDF tarjado disponível.", 400

    return send_file(path, as_attachment=True, download_name="documento_tarjado.pdf", mimetype="application/pdf")



@app.route("/tarjar_txt", methods=["GET", "POST"])
def tarjar_txt_preview():
    if request.method == "POST":
        arquivo = request.files.get("txtfile")
        selecionados = request.form.getlist("itens")

        if not arquivo or not arquivo.filename.endswith(".txt"):
            return "Arquivo inválido. Envie um .txt.", 400

        conteudo = arquivo.read().decode("utf-8")
        padroes_ativos = {k: v for k, v in PADROES_SENSIVEIS.items() if k in selecionados}

        ocorrencias = []
        for tipo, regex in padroes_ativos.items():
            for m in re.finditer(regex, conteudo):
                ocorrencias.append({
                    "tipo": tipo,
                    "texto": m.group(),
                    "start": m.start(),
                    "end": m.end(),
                    "id": f"{m.start()}_{m.end()}"
                })

        session["conteudo"] = conteudo
        session["ocorrencias"] = ocorrencias

        return render_template("preview_txt.html", conteudo=conteudo, ocorrencias=ocorrencias)

    return render_template("tarjar_txt.html", padroes=PADROES_SENSIVEIS.keys())



@app.route("/aplicar_tarjas_txt", methods=["POST"])
def aplicar_tarjas_txt():
    conteudo = session.get("conteudo", "")
    ocorrencias = session.get("ocorrencias", [])
    selecionados = request.form.getlist("selecionados")

    deslocamento = 0
    for item in ocorrencias:
        if f"{item['start']}_{item['end']}" in selecionados:
            inicio = item["start"] + deslocamento
            fim = item["end"] + deslocamento
            comprimento = fim - inicio
            substituto = "█" * comprimento
            conteudo = conteudo[:inicio] + substituto + conteudo[fim:]
            deslocamento += len(substituto) - (fim - inicio)

    temp_file = tempfile.NamedTemporaryFile(delete=False, mode="w+", encoding="utf-8", suffix="_tarjado.txt")
    temp_file.write(conteudo)
    temp_file.close()

    return send_file(temp_file.name, as_attachment=True, download_name="arquivo_tarjado.txt")



#Função ainda indiponível
