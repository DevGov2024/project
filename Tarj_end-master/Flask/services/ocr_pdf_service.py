import io
import os
import uuid
import json
import base64
import re
from PIL import ImageDraw
from pdf2image import convert_from_bytes
import pytesseract
from fuzzywuzzy import fuzz

class OcrPdfService:
    @staticmethod
    def processar_ocr_pdf(request, app, PADROES_SENSIVEIS, session):
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

        imagens_tarjadas = [img.copy() for img in imagens]
        todas_ocorrencias = []

        # --- OCR automático ---
        for idx, imagem in enumerate(imagens_tarjadas):
            todas_ocorrencias += OcrPdfService._detectar_ocorrencias(imagem, padroes_ativos, idx, app)

        # --- Tarjas manuais digitadas pelo usuário ---
        texto_manual = request.form.get('tarjas_manualmente_adicionadas', '').strip()
        if texto_manual:
            trechos = [t.strip().lower() for t in texto_manual.split('|') if t.strip()]
            for idx, imagem in enumerate(imagens_tarjadas):
                todas_ocorrencias += OcrPdfService._aplicar_tarjas_manuais_texto(imagem, trechos, idx)

        # --- Tarjas manuais via coordenadas ---
        tarjas_manuais_str = request.form.get('tarjas_manuais', '[]')
        imagens_tarjadas = OcrPdfService._aplicar_tarjas_coordenadas(imagens_tarjadas, tarjas_manuais_str, app)

        # --- Salvar PDF temporário ---
        pdf_tarjado, caminho_arquivo, pdf_base64 = OcrPdfService._salvar_pdf_temporario(imagens_tarjadas, app)

        session['ocr_pdf_path'] = caminho_arquivo
        session['ocr_ocorrencias'] = todas_ocorrencias

        return pdf_base64, todas_ocorrencias

    @staticmethod
    def aplicar_tarjas(request, session):
        caminho = session.get('ocr_pdf_path')
        ocorrencias_automaticas = session.get('ocr_ocorrencias', [])

        if not caminho or not os.path.exists(caminho):
            return None, "Arquivo OCR não encontrado.", 400

        imagens = convert_from_bytes(open(caminho, 'rb').read())
        imagens_tarjadas = [img.copy() for img in imagens]

        selecionados = request.form.getlist('selecionados')
        selecionados_set = set(str(s) for s in selecionados)

        texto_manual = request.form.get('tarjas_manualmente_adicionadas', '').strip()
        trechos_manuais = [t.strip().lower() for t in texto_manual.split('|') if t.strip()]

        tarjas_aplicadas = OcrPdfService._aplicar_tarjas(imagens_tarjadas, ocorrencias_automaticas, selecionados_set, trechos_manuais)

        session['tarjas_ocr'] = tarjas_aplicadas

        buffer = io.BytesIO()
        imagens_tarjadas[0].save(buffer, format="PDF", save_all=True, append_images=imagens_tarjadas[1:])
        buffer.seek(0)

        return buffer, None, 200

    @staticmethod
    def atualizar_preview(request, session):
        try:
            data = request.get_json(force=True)
            selecionados = data.get("selecionados", [])
            trechos_manuais = data.get("manuais", [])

            selecionados_set = set(str(s) for s in selecionados)

            caminho = session.get('ocr_pdf_path')
            ocorrencias = session.get('ocr_ocorrencias', [])

            if not caminho or not os.path.exists(caminho):
                return {"erro": "Arquivo temporário não encontrado."}, 400

            imagens = convert_from_bytes(open(caminho, 'rb').read())
            imagens_tarjadas = [img.copy() for img in imagens]

            tarjas_aplicadas = OcrPdfService._aplicar_tarjas(imagens_tarjadas, ocorrencias, selecionados_set, trechos_manuais)

            session['tarjas_ocr'] = tarjas_aplicadas

            pdf_mem = io.BytesIO()
            imagens_tarjadas[0].save(pdf_mem, format="PDF", save_all=True, append_images=imagens_tarjadas[1:])
            pdf_mem.seek(0)
            pdf_b64 = base64.b64encode(pdf_mem.read()).decode('utf-8')

            return {"pdf_data": pdf_b64}, 200

        except Exception as e:
            return {"erro": str(e)}, 500

    # ======================
    # Funções auxiliares privadas
    # ======================

    @staticmethod
    def _detectar_ocorrencias(imagem, padroes_ativos, idx, app):
        draw = ImageDraw.Draw(imagem)
        dados_ocr = pytesseract.image_to_data(imagem, lang='por', output_type=pytesseract.Output.DICT)
        ocorrencias = []

        for tipo, regex in padroes_ativos.items():
            try:
                pattern = regex if isinstance(regex, re.Pattern) else re.compile(regex, re.IGNORECASE | re.UNICODE)
            except re.error as e:
                app.logger.error(f"Regex inválido para tipo '{tipo}': {e}")
                continue

            for i, palavra in enumerate(dados_ocr['text']):
                texto = (palavra or '').strip()
                if not texto:
                    continue
                if pattern.search(texto):
                    x, y, w, h = int(dados_ocr['left'][i]), int(dados_ocr['top'][i]), int(dados_ocr['width'][i]), int(dados_ocr['height'][i])
                    draw.rectangle([(x, y), (x + w, y + h)], fill='black')
                    ocorrencias.append({"id": str(uuid.uuid4()), "pagina": idx, "tipo": tipo, "texto": texto})
        return ocorrencias

    @staticmethod
    def _aplicar_tarjas_manuais_texto(imagem, trechos, idx):
        draw = ImageDraw.Draw(imagem)
        dados_ocr = pytesseract.image_to_data(imagem, lang='por', output_type=pytesseract.Output.DICT)
        ocorrencias = []

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

        for trecho in trechos:
            trecho_lower = trecho.lower()
            for palavras_linha in linhas.values():
                linha_texto = ' '.join([p['text'] for p in palavras_linha]).lower()
                start_pos = linha_texto.find(trecho_lower)
                if start_pos != -1:
                    char_count = 0
                    palavras_a_tarjar = []
                    for palavra in palavras_linha:
                        palavra_len = len(palavra['text'])
                        palavra_start = char_count
                        palavra_end = char_count + palavra_len
                        if (palavra_end > start_pos) and (palavra_start < start_pos + len(trecho_lower)):
                            palavras_a_tarjar.append(palavra)
                        char_count += palavra_len + 1
                    for palavra in palavras_a_tarjar:
                        x, y, w, h = int(palavra['left']), int(palavra['top']), int(palavra['width']), int(palavra['height'])
                        draw.rectangle([(x, y), (x + w, y + h)], fill='black')
                    ocorrencias.append({"id": str(uuid.uuid4()), "pagina": idx, "tipo": "manual", "texto": trecho})
        return ocorrencias

    @staticmethod
    def _aplicar_tarjas_coordenadas(imagens, tarjas_manuais_str, app):
        try:
            tarjas_manuais = json.loads(tarjas_manuais_str)
            if not isinstance(tarjas_manuais, list):
                raise ValueError()
        except (json.JSONDecodeError, ValueError):
            app.logger.error("tarjas_manuais inválido")
            tarjas_manuais = []

        for tarja in tarjas_manuais:
            pagina, x, y, w, h = tarja.get('pagina'), tarja.get('x'), tarja.get('y'), tarja.get('w'), tarja.get('h')
            if isinstance(pagina, int) and 0 <= pagina < len(imagens) and all(isinstance(c, (int, float)) for c in [x, y, w, h]):
                draw = ImageDraw.Draw(imagens[pagina])
                draw.rectangle([(int(x), int(y)), (int(x + w), int(y + h))], fill='black')
            else:
                app.logger.warning(f"Tarja manual inválida ignorada: {tarja}")
        return imagens

    @staticmethod
    def _salvar_pdf_temporario(imagens, app):
        pdf_mem = io.BytesIO()
        try:
            imagens[0].save(pdf_mem, format="PDF", save_all=True, append_images=imagens[1:])
        except Exception as e:
            app.logger.error(f"Erro ao salvar PDF temporário: {e}")
            raise
        pdf_mem.seek(0)

        diretorio_temp = os.path.join(app.root_path, 'arquivos_temp')
        os.makedirs(diretorio_temp, exist_ok=True)
        nome_arquivo = f"{uuid.uuid4()}.pdf"
        caminho_arquivo = os.path.join(diretorio_temp, nome_arquivo)
        with open(caminho_arquivo, 'wb') as f:
            f.write(pdf_mem.read())
        pdf_mem.seek(0)
        pdf_base64 = base64.b64encode(pdf_mem.read()).decode('utf-8')
        return pdf_mem, caminho_arquivo, pdf_base64

    @staticmethod
    def _aplicar_tarjas(imagens_tarjadas, ocorrencias_automaticas, selecionados_set, trechos_manuais):
        tarjas_aplicadas = []
        for idx, imagem in enumerate(imagens_tarjadas):
            draw = ImageDraw.Draw(imagem)
            dados_ocr = pytesseract.image_to_data(imagem, lang='por', output_type=pytesseract.Output.DICT)

            linhas = {}
            for i in range(len(dados_ocr['text'])):
                linha_num = dados_ocr['line_num'][i]
                if linha_num not in linhas:
                    linhas[linha_num] = []
                linhas[linha_num].append({
                    'text': (dados_ocr['text'][i] or '').strip(),
                    'left': int(dados_ocr['left'][i]),
                    'top': int(dados_ocr['top'][i]),
                    'width': int(dados_ocr['width'][i]),
                    'height': int(dados_ocr['height'][i])
                })

            # Tarjas automáticas
            for ocorrencia in [o for o in ocorrencias_automaticas if o['pagina'] == idx]:
                if str(ocorrencia['id']) not in selecionados_set:
                    continue
                termo_lower = ocorrencia['texto'].lower()
                for palavras_linha in linhas.values():
                    linha_texto = ' '.join([p['text'] for p in palavras_linha]).lower()
                    if termo_lower in linha_texto:
                        char_count = 0
                        for palavra in palavras_linha:
                            palavra_start = char_count
                            palavra_end = char_count + len(palavra['text'])
                            char_count += len(palavra['text']) + 1
                            trecho_start = linha_texto.find(termo_lower)
                            trecho_end = trecho_start + len(termo_lower)
                            if palavra_end > trecho_start and palavra_start < trecho_end:
                                x, y, w, h = palavra['left'], palavra['top'], palavra['width'], palavra['height']
                                draw.rectangle([(x, y), (x + w, y + h)], fill='black')
                                tarjas_aplicadas.append({'pagina': idx, 'texto': palavra['text']})

            # Tarjas manuais
            for trecho in trechos_manuais:
                trecho_lower = trecho.lower()
                for palavras_linha in linhas.values():
                    linha_texto = ' '.join([p['text'] for p in palavras_linha]).lower()
                    if fuzz.partial_ratio(trecho_lower, linha_texto) >= 85:
                        char_count = 0
                        for palavra in palavras_linha:
                            palavra_start = char_count
                            palavra_end = char_count + len(palavra['text'])
                            char_count += len(palavra['text']) + 1
                            trecho_start = linha_texto.find(trecho_lower)
                            trecho_end = trecho_start + len(trecho_lower)
                            if palavra_end > trecho_start and palavra_start < trecho_end:
                                x, y, w, h = palavra['left'], palavra['top'], palavra['width'], palavra['height']
                                draw.rectangle([(x, y), (x + w, y + h)], fill='black')
                                tarjas_aplicadas.append({'pagina': idx, 'texto': palavra['text']})

        return tarjas_aplicadas
