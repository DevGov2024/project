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
import json
from fuzzywuzzy import fuzz
from pdf2image import convert_from_bytes
import pytesseract

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
        paragrafos_com_tarja = []

        for i, par in enumerate(doc.paragraphs):
            texto = par.text
            texto_tarjado = texto  # manter original para sobrescrever com tarjas
            offset = 0  # controle de deslocamento conforme o texto é alterado

            for tipo, regex in padroes_ativos.items():
                for m in re.finditer(regex, texto):
                    encontrado = m.group()
                    inicio = m.start() + offset
                    fim = m.end() + offset
                    tarja = '█' * len(encontrado)
                    texto_tarjado = (
                        texto_tarjado[:inicio] + tarja + texto_tarjado[fim:]
                    )

                    # Atualiza o offset após substituir
                    offset += len(tarja) - len(encontrado)

                    ocorrencias.append({
                        "tipo": tipo,
                        "texto": encontrado,
                        "paragrafo": i,
                        "start": m.start(),
                        "end": m.end(),
                        "id": f"{i}_{m.start()}_{m.end()}"
                    })

            paragrafos_com_tarja.append(texto_tarjado)

        # Salva cópia temporária do original para edição posterior
        temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".docx").name
        with open(temp_path, "wb") as f:
            f.write(conteudo_bytes)

        session['doc_ocorrencias'] = ocorrencias
        session['doc_path'] = temp_path

        return render_template("preview_docx.html", ocorrencias=ocorrencias, paragrafos=paragrafos_com_tarja)

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


@app.route('/tarjar_ocr_pdf', methods=['GET', 'POST'])
def tarjar_ocr_pdf():
    if request.method == 'POST':
        arquivo = request.files.get('ocrpdf')
        tipos_selecionados = request.form.getlist('tipos')

        if not arquivo or not arquivo.filename.lower().endswith('.pdf'):
            return "Arquivo inválido. Envie um arquivo PDF escaneado.", 400

        padroes_ativos = {k: v for k, v in PADROES_SENSIVEIS.items() if k in tipos_selecionados}

        try:
            pdf_bytes = arquivo.read()
            imagens = convert_from_bytes(pdf_bytes)
        except Exception as e:
            app.logger.error(f"Erro ao converter PDF em imagens: {e}")
            return "Erro ao processar o arquivo PDF.", 500

        imagens_tarjadas = []
        todas_ocorrencias = []

        # Primeiro cria cópia das imagens para manipular
        for imagem in imagens:
            imagens_tarjadas.append(imagem.copy())

        # TARJAS AUTOMÁTICAS COM REGEX
        for idx, imagem in enumerate(imagens_tarjadas):
            dados_ocr = pytesseract.image_to_data(imagem, lang='por', output_type=pytesseract.Output.DICT)
            draw = ImageDraw.Draw(imagem)

            for tipo, regex in padroes_ativos.items():
                try:
                    pattern = re.compile(regex, re.IGNORECASE | re.UNICODE)
                except re.error as e:
                    app.logger.error(f"Regex inválido para tipo '{tipo}': {e}")
                    continue

                for i, palavra in enumerate(dados_ocr['text']):
                    texto = (palavra or '').strip()
                    if not texto:
                        continue

                    if pattern.search(texto):
                        x = int(dados_ocr['left'][i])
                        y = int(dados_ocr['top'][i])
                        w = int(dados_ocr['width'][i])
                        h = int(dados_ocr['height'][i])
                        draw.rectangle([(x, y), (x + w, y + h)], fill='black')

                        todas_ocorrencias.append({
                            "pagina": idx,
                            "tipo": tipo,
                            "texto": texto
                        })


        # --- BUSCA MANUAL POR TEXTO DIGITADO PELO USUÁRIO ---
        texto_manual = request.form.get('tarjas_manualmente_adicionadas', '').strip()
        if texto_manual:
            trechos_manualmente_adicionados = [t.strip().lower() for t in texto_manual.split('|') if t.strip()]

            for idx, imagem in enumerate(imagens_tarjadas):
                dados_ocr = pytesseract.image_to_data(imagem, lang='por', output_type=pytesseract.Output.DICT)
                draw = ImageDraw.Draw(imagem)

                # Agrupar palavras por linha
                linhas = {}
                for i in range(len(dados_ocr['text'])):
                    linha = dados_ocr['line_num'][i]
                    if linha not in linhas:
                        linhas[linha] = []
                    linhas[linha].append({
                        'text': (dados_ocr['text'][i] or '').strip(),
                        'left': dados_ocr['left'][i],
                        'top': dados_ocr['top'][i],
                        'width': dados_ocr['width'][i],
                        'height': dados_ocr['height'][i]
                    })

                # Verifica cada trecho manual por linha
                for trecho in trechos_manualmente_adicionados:
                    for palavras_linha in linhas.values():
                        frase = ' '.join([p['text'] for p in palavras_linha]).lower()
                        if trecho in frase:
                            for palavra in palavras_linha:
                                if palavra['text']:
                                    x = int(palavra['left'])
                                    y = int(palavra['top'])
                                    w = int(palavra['width'])
                                    h = int(palavra['height'])
                                    draw.rectangle([(x, y), (x + w, y + h)], fill='black')
                            todas_ocorrencias.append({
                                "pagina": idx,
                                "tipo": "manual",
                                "texto": trecho
                            })


        # --- TARJAS MANUAIS (coordenadas) ---
        tarjas_manuais_str = request.form.get('tarjas_manuais', '[]')
        try:
            tarjas_manuais = json.loads(tarjas_manuais_str)
            if not isinstance(tarjas_manuais, list):
                raise ValueError("tarjas_manuais não é uma lista")
        except (json.JSONDecodeError, ValueError) as e:
            app.logger.error(f"Erro ao ler tarjas manuais JSON: {e}")
            tarjas_manuais = []

        for tarja in tarjas_manuais:
            pagina = tarja.get('pagina')
            x = tarja.get('x')
            y = tarja.get('y')
            w = tarja.get('w')
            h = tarja.get('h')

            if (
                isinstance(pagina, int) and 0 <= pagina < len(imagens_tarjadas) and
                all(isinstance(coord, (int, float)) for coord in [x, y, w, h])
            ):
                draw = ImageDraw.Draw(imagens_tarjadas[pagina])
                draw.rectangle([(int(x), int(y)), (int(x + w), int(y + h))], fill='black')
            else:
                app.logger.warning(f"Tarja manual inválida ignorada: {tarja}")

        # --- FINALIZA PDF TARJADO ---
        pdf_tarjado = io.BytesIO()
        try:
            imagens_tarjadas[0].save(pdf_tarjado, format="PDF", save_all=True, append_images=imagens_tarjadas[1:])
        except Exception as e:
            app.logger.error(f"Erro ao salvar PDF tarjado: {e}")
            return "Erro ao gerar o PDF tarjado.", 500

        pdf_tarjado.seek(0)

        diretorio_temp = os.path.join(app.root_path, 'arquivos_temp')
        os.makedirs(diretorio_temp, exist_ok=True)
        nome_arquivo = f"{uuid.uuid4()}.pdf"
        caminho_arquivo = os.path.join(diretorio_temp, nome_arquivo)

        with open(caminho_arquivo, 'wb') as f:
            f.write(pdf_tarjado.read())

        pdf_tarjado.seek(0)
        pdf_base64 = base64.b64encode(pdf_tarjado.read()).decode('utf-8')

        session['ocr_pdf_path'] = caminho_arquivo
        session['ocr_ocorrencias'] = todas_ocorrencias

        return render_template(
            "preview_ocr.html",
            ocorrencias=todas_ocorrencias,
            pdf_b64=pdf_base64
        )

    return render_template('tarjar_ocr_pdf.html', padroes=PADROES_SENSIVEIS.keys())

@app.route('/aplicar_tarjas_ocr_pdf', methods=['POST'])
def aplicar_tarjas_ocr_pdf():
    caminho = session.get('ocr_pdf_path')
    if not caminho or not os.path.exists(caminho):
        return "Arquivo OCR não encontrado.", 400

    imagens = convert_from_bytes(open(caminho, 'rb').read())
    imagens_tarjadas = [img.copy() for img in imagens]

    texto_manual = request.form.get('tarjas_manualmente_adicionadas', '').strip()
    if not texto_manual:
        return "Nenhum trecho manual enviado.", 400

    trechos = [t.strip().lower() for t in texto_manual.split('|') if t.strip()]
    print("🧠 Tarjas manuais recebidas:", trechos)

    tarjas_aplicadas = []

    for idx, imagem in enumerate(imagens_tarjadas):
        dados_ocr = pytesseract.image_to_data(imagem, lang='por', output_type=pytesseract.Output.DICT)
        draw = ImageDraw.Draw(imagem)

        palavras = zip(
            dados_ocr['text'], dados_ocr['left'], dados_ocr['top'],
            dados_ocr['width'], dados_ocr['height'], dados_ocr['line_num']
        )

        linhas = {}
        for text, left, top, width, height, line in palavras:
            if not text.strip():
                continue
            if line not in linhas:
                linhas[line] = []
            linhas[line].append({
                'text': text.strip(),
                'left': int(left),
                'top': int(top),
                'width': int(width),
                'height': int(height)
            })

        for trecho in trechos:
            for linha in linhas.values():
                linha_texto = ' '.join(p['text'].lower() for p in linha if p['text'])
                similaridade = fuzz.ratio(trecho, linha_texto)

                if similaridade >= 92:  # mais rigoroso
                    for palavra in linha:
                        x, y = palavra['left'], palavra['top']
                        w, h = palavra['width'], palavra['height']
                        draw.rectangle([(x, y), (x + w, y + h)], fill="black")
                        tarjas_aplicadas.append({
                            'page': idx,
                            'coords': (x, y, x + w, y + h),
                            'original_text': palavra['text']
                        })

    session['tarjas_ocr'] = tarjas_aplicadas

    buffer = io.BytesIO()
    imagens_tarjadas[0].save(buffer, format="PDF", save_all=True, append_images=imagens_tarjadas[1:])
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="documento_tarjado.pdf",
        mimetype="application/pdf"
    )

@app.route('/download_pdf_ocr')
def download_pdf_ocr():
    caminho = session.get('ocr_pdf_path')

    if not caminho or not os.path.exists(caminho):
        return "Arquivo não encontrado.", 404

    return send_file(caminho, as_attachment=True, download_name="pdf_tarjado_ocr.pdf")


@app.route('/ver_pdf_ocr')
def ver_pdf_ocr():
    caminho = session.get('ocr_pdf_path')
    if not caminho or not os.path.exists(caminho):
        return "Arquivo não encontrado.", 404

    return send_file(caminho, mimetype='application/pdf')
