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
from pdf2image import convert_from_bytes
import pytesseract
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

        # Salvar o arquivo em disco temporariamente
        temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".docx").name
        with open(temp_path, "wb") as f:
            f.write(conteudo_bytes)

        # Guardar só o caminho e as ocorrências na sessão
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
            texto = doc.paragraphs[par_index].text

            antes = texto[:item["start"]]
            depois = texto[item["end"]:]
            novo_texto = antes + f"[TARJADO-{item['tipo']}]" + depois

            doc.paragraphs[par_index].text = novo_texto

    mem_file = io.BytesIO()
    doc.save(mem_file)
    mem_file.seek(0)

    # (Opcional) deletar arquivo temporário
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
    "CNPJ": r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b',
    "CARTAO": r'(?:\d[ -]*?){13,16}',
    "PLACA": r'\b[A-Z]{3}-?\d{1}[A-Z0-9]{1}\d{2}\b',
    "DATA": r'\b\d{2}/\d{2}/\d{4}\b',
    "CEP": r'\d{5}-\d{3}',
    "endereço": r"\b(?:Rua|Av|Avenida|Travessa|Estrada|Rodovia|R\.|Av\.?)\.?\s+[A-Za-zÀ-ÖØ-öø-ÿ0-9\s]+,\s*\d+"
   
}


def aplicar_tarjas_em_pdf(doc, padroes):
    for pagina in doc:
        texto = pagina.get_text("text")
        for nome, regex in padroes.items():
            for match in re.finditer(regex, texto):
                termo = match.group()
                areas = pagina.search_for(termo)
                for area in areas:
                    pagina.add_redact_annot(area, fill=(0, 0, 0))
        pagina.apply_redactions()
    return doc 

@app.route('/tarjar_pdf', methods=['GET', 'POST'])
def tarjar_pdf():
    if request.method == 'POST':
        arquivo = request.files.get('pdffile')
        selecionados = request.form.getlist('itens')

        if not arquivo or not arquivo.filename.endswith('.pdf'):
            return "Arquivo inválido. Envie um .pdf.", 400

        padroes_ativos = {k: v for k, v in PADROES_SENSIVEIS_PDF.items() if k in selecionados}

        pdf_bytes = arquivo.read()
        doc = fitz.open("pdf", pdf_bytes)
        aplicar_tarjas_em_pdf(doc, padroes_ativos)

        mem_file = io.BytesIO()
        doc.save(mem_file)
        mem_file.seek(0)
        doc.close()

        # Salvar o PDF em arquivo temporário
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp_file.write(mem_file.read())
        temp_file.close()

       
        session['pdf_tarjado_path'] = temp_file.name

        
        with open(temp_file.name, 'rb') as f:
            pdf_b64 = base64.b64encode(f.read()).decode('utf-8')

        return render_template('preview_pdf.html', pdf_data=pdf_b64)

    return render_template('tarjar_pdf.html', padroes=PADROES_SENSIVEIS_PDF.keys())


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
            substituto = f"[TARJADO-{item['tipo']}]"
            conteudo = conteudo[:inicio] + substituto + conteudo[fim:]
            deslocamento += len(substituto) - (fim - inicio)

    temp_file = tempfile.NamedTemporaryFile(delete=False, mode="w+", encoding="utf-8", suffix="_tarjado.txt")
    temp_file.write(conteudo)
    temp_file.close()

    return send_file(temp_file.name, as_attachment=True, download_name="arquivo_tarjado.txt")






#Função ainda indiponível
os.environ['TESSDATA_PREFIX'] = r"C:\Program Files\Tesseract-OCR"
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

@app.route('/tarjar_pdf_ocr', methods=['GET', 'POST'])
def tarjar_pdf_ocr():
    if request.method == 'POST':
        arquivo = request.files.get('pdffile')
        selecionados = request.form.getlist('itens')

        if not arquivo or not arquivo.filename.endswith('.pdf'):
            return "Arquivo inválido. Envie um .pdf.", 400

        padroes_ativos = {k: v for k, v in PADROES_SENSIVEIS_PDF.items() if k in selecionados}
        poppler_path = r"C:\Program Files\Release-24.08.0-0\poppler-24.08.0\Library\bin"

        # Converte PDF em imagens
        imagens = convert_from_bytes(arquivo.read(), poppler_path=poppler_path)

        imagens_tarjadas = []

        for img in imagens:
            texto = pytesseract.image_to_string(img, lang='por')

            # Copia da imagem para desenhar
            draw_img = img.copy()
            draw = ImageDraw.Draw(draw_img)

            # Dados com posição
            data = pytesseract.image_to_data(img, lang='por', output_type=pytesseract.Output.DICT)

            for tipo, regex in padroes_ativos.items():
                matches = re.finditer(regex, texto)
                for match in matches:
                    termo = match.group()
                    # Tenta encontrar o termo nas palavras detectadas
                    for i, word in enumerate(data['text']):
                        if word and termo.startswith(word):
                            x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                            draw.rectangle([x, y, x + w, y + h], fill='black')

            imagens_tarjadas.append(draw_img)

        # Salva como novo PDF
        temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        imagens_tarjadas[0].save(temp_pdf.name, save_all=True, append_images=imagens_tarjadas[1:])

        session['pdf_tarjado_path'] = temp_pdf.name

        with open(temp_pdf.name, 'rb') as f:
            pdf_b64 = base64.b64encode(f.read()).decode('utf-8')

        return render_template('revisar_termos.html', pdf_data=pdf_b64)

    return render_template('tarjar_pdf_ocr.html', padroes=PADROES_SENSIVEIS_PDF.keys())