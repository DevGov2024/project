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
    "RG":  r'\d{2}\.\d{3}\.\d{3}-\d{1}',
    "EMAIL": r'\b[\w\.-]+@[\w\.-]+\.\w{2,}\b',
    "TELEFONE": r'\(?\d{2}\)?[\s-]?\d{4,5}-\d{4}',
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

    paragrafo_edits = {}

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

    if trechos_manuais:
        for i, par in enumerate(doc.paragraphs):
            texto = paragrafo_edits.get(i, par.text)
            for trecho_manual in trechos_manuais:
                if trecho_manual in texto:
                    texto = texto.replace(trecho_manual, "█" * len(trecho_manual))
                    paragrafo_edits[i] = texto

    for i, novo_texto in paragrafo_edits.items():
        par = doc.paragraphs[i]
        par.clear()
        run = par.add_run(novo_texto)
        run.font.color.rgb = RGBColor(0, 0, 0)

    mem_file = io.BytesIO()
    doc.save(mem_file)
    mem_file.seek(0)

    # NÃO REMOVER o arquivo aqui! Senão o send_file não encontra.
    # os.remove(caminho)

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
    preservar_logo = request.form.get('preservar_logo', '0') == '1'

    trechos_manuais_raw = request.form.get('tarjas_manualmente_adicionadas', '')
    trechos_manuais = [t.strip() for t in trechos_manuais_raw.split('|') if t.strip()]

    caminho = session.get('pdf_path')
    ocorrencias = session.get('pdf_ocorrencias', [])

    if not caminho or not os.path.exists(caminho):
        return "Erro: arquivo temporário não encontrado.", 400

    doc = fitz.open(caminho)
    redactions_por_pagina = {}

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

    for pagina_idx, areas in redactions_por_pagina.items():
        pagina = doc[pagina_idx]
        for area in areas:
            pagina.add_redact_annot(area, fill=(0, 0, 0))
        pagina.apply_redactions()

    mem_file = io.BytesIO()
    doc.save(mem_file)
    mem_file.seek(0)
    doc.close()

    # NÃO remover o arquivo temporário aqui para evitar erro
    # os.remove(caminho)

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

        for imagem in imagens:
            imagens_tarjadas.append(imagem.copy())

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
                            "id": str(uuid.uuid4()),
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

                for trecho in trechos_manualmente_adicionados:
                    trecho_lower = trecho.lower()
                    for palavras_linha in linhas.values():
                        # cria o texto completo da linha com espaços, também lower
                        linha_texto = ' '.join([p['text'] for p in palavras_linha]).lower()

                        start_pos = linha_texto.find(trecho_lower)
                        if start_pos != -1:
                            # agora vamos mapear o trecho para as palavras que correspondem
                            char_count = 0
                            palavras_a_tarjar = []

                            for palavra in palavras_linha:
                                palavra_texto = palavra['text']
                                palavra_len = len(palavra_texto)
                                # posição inicial e final da palavra no texto da linha
                                palavra_start = char_count
                                palavra_end = char_count + palavra_len

                                # Verifica se a palavra está dentro do trecho a tarjar
                                trecho_end_pos = start_pos + len(trecho_lower)

                                # Condição: palavra intersecta o trecho a tarjar
                                if (palavra_end > start_pos) and (palavra_start < trecho_end_pos):
                                    palavras_a_tarjar.append(palavra)

                                # atualiza contador (considera espaço depois da palavra)
                                char_count += palavra_len + 1

                            # pinta só as palavras dentro do trecho
                            for palavra in palavras_a_tarjar:
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

        # Salvar PDF temporário
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
    ocorrencias_automaticas = session.get('ocr_ocorrencias', [])

    if not caminho or not os.path.exists(caminho):
        return "Arquivo OCR não encontrado.", 400

    imagens = convert_from_bytes(open(caminho, 'rb').read())
    imagens_tarjadas = [img.copy() for img in imagens]

    # IDs selecionados via checkbox
    selecionados = request.form.getlist('selecionados')
    selecionados_set = set(selecionados)

    # Trechos manuais recebidos do formulário
    texto_manual = request.form.get('tarjas_manualmente_adicionadas', '').strip()
    trechos_manuais = [t.strip().lower() for t in texto_manual.split('|') if t.strip()]

    tarjas_aplicadas = []

    for idx, imagem in enumerate(imagens_tarjadas):
        dados_ocr = pytesseract.image_to_data(imagem, lang='por', output_type=pytesseract.Output.DICT)
        draw = ImageDraw.Draw(imagem)

        blocos = {}
        for i in range(len(dados_ocr['text'])):
            palavra = (dados_ocr['text'][i] or '').strip()
            if not palavra:
                continue
            bloco_id = (dados_ocr['block_num'][i], dados_ocr['line_num'][i])
            if bloco_id not in blocos:
                blocos[bloco_id] = []
            blocos[bloco_id].append({
                'text': palavra,
                'left': int(dados_ocr['left'][i]),
                'top': int(dados_ocr['top'][i]),
                'width': int(dados_ocr['width'][i]),
                'height': int(dados_ocr['height'][i])
            })

        # Aplica tarjas só nas ocorrências selecionadas
        for ocorrencia in [o for o in ocorrencias_automaticas if o.get('pagina') == idx]:
            if str(ocorrencia.get('id')) not in selecionados_set:
                continue
            for palavras_linha in blocos.values():
                frase = ' '.join([p['text'] for p in palavras_linha]).lower()
                if ocorrencia['texto'].lower() in frase:
                    for palavra in palavras_linha:
                        x, y, w, h = palavra['left'], palavra['top'], palavra['width'], palavra['height']
                        draw.rectangle([(x, y), (x + w, y + h)], fill='black')
                        tarjas_aplicadas.append({'pagina': idx, 'texto': palavra['text']})

        # Aplica tarjas manuais (igual seu código)
        for trecho in trechos_manuais:
            for palavras_linha in blocos.values():
                frase = ' '.join([p['text'] for p in palavras_linha]).lower()
                similaridade = fuzz.partial_ratio(trecho, frase)
                if similaridade >= 85:
                    for palavra in palavras_linha:
                        x, y, w, h = palavra['left'], palavra['top'], palavra['width'], palavra['height']
                        draw.rectangle([(x, y), (x + w, y + h)], fill='black')
                        tarjas_aplicadas.append({'pagina': idx, 'texto': palavra['text']})

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