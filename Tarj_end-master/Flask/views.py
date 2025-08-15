from main import app
from flask import Flask, render_template, request, send_file, redirect, url_for, session, jsonify
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
from pyzbar.pyzbar import decode
from PIL import Image
from PIL import Image, ImageDraw
from services.ocr_pdf_service import OcrPdfService
from regex_patterns import PADROES_SENSIVEIS
import re
from flask import jsonify, session
from docx import Document
from services.docx_service import encontrar_ocorrencias_docx, aplicar_tarjas_docx, atualizar_preview_docx
from services.pdf_service import gerar_preview_pdf, aplicar_tarjas_pdf, atualizar_preview_pdf
# Habilita sessão para guardar dados temporários
app.secret_key = "segredo-muito-seguro"

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

PADROES_SENSIVEIS = {
    "CPF": r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
    "RG": r"\b\d{2}\.\d{3}\.\d{3}-\d{1}\b"
}
# ----------------------------------------------------------------------------------- Padrões para DOCX ----------------------------------------------------------------------------------

@app.route('/tarjar_docx', methods=['GET', 'POST'])
def tarjar_docx_preview():
    if request.method == 'POST':
        arquivo = request.files.get("docxfile")
        selecionados = request.form.getlist("itens")

        if not arquivo or not arquivo.filename.endswith('.docx'):
            return "Arquivo inválido. Envie um .docx.", 400

        padroes_ativos = {k: v for k, v in PADROES_SENSIVEIS.items() if k in selecionados}

        conteudo_bytes = arquivo.read()
        ocorrencias, paragrafos, temp_path = encontrar_ocorrencias_docx(conteudo_bytes, padroes_ativos)

        session['doc_ocorrencias'] = ocorrencias
        session['doc_path'] = temp_path

        return render_template("preview_docx.html", ocorrencias=ocorrencias, paragrafos=paragrafos)

    return render_template("tarjar_docx.html", padroes=PADROES_SENSIVEIS.keys())


@app.route("/aplicar_tarjas_docx", methods=["POST"])
def aplicar_tarjas_docx_route():
    selecionados = request.form.getlist("selecionados")
    trechos_manuais_raw = request.form.get("tarjas_manualmente_adicionadas", "")
    trechos_manuais = [t.strip() for t in trechos_manuais_raw.split("|") if t.strip()]

    ocorrencias = session.get("doc_ocorrencias", [])
    caminho = session.get("doc_path", None)

    if not caminho or not os.path.exists(caminho):
        return "Erro: Arquivo temporário não encontrado.", 400

    mem_file = aplicar_tarjas_docx(caminho, ocorrencias, selecionados, trechos_manuais)

    return send_file(
        mem_file,
        as_attachment=True,
        download_name="documento_tarjado.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

@app.route("/atualizar_preview_docx", methods=["POST"])
def atualizar_preview_docx_route():
    try:
        data = request.get_json(force=True)
        selecionados = set(data.get("selecionados", []))
        trechos_manuais = data.get("manuais", [])

        ocorrencias = session.get("doc_ocorrencias", [])
        caminho = session.get("doc_path", None)

        if not caminho or not os.path.exists(caminho):
            return jsonify({"erro": "Arquivo temporário não encontrado."}), 400

        paragrafos_atualizados = atualizar_preview_docx(caminho, ocorrencias, selecionados, trechos_manuais)

        return jsonify({"paragrafos": paragrafos_atualizados})

    except Exception as e:
        return jsonify({"erro": f"Erro no servidor: {str(e)}"}), 500

# ----------------------------------------------------------------------------------- Padrões para PDF ----------------------------------------------------------------------------------

@app.route('/tarjar_pdf', methods=['GET', 'POST'])
def tarjar_pdf_route():
    if request.method == 'POST':
        arquivo = request.files.get('pdffile')
        tipos_selecionados = request.form.getlist('tipos')

        if not arquivo or not arquivo.filename.endswith('.pdf'):
            return "Arquivo inválido. Envie um .pdf.", 400

        padroes_ativos = {k: v for k, v in PADROES_SENSIVEIS.items() if k in tipos_selecionados}

        pdf_bytes = arquivo.read()
        ocorrencias, pdf_b64, temp_path = gerar_preview_pdf(pdf_bytes, padroes_ativos)

        session['pdf_path'] = temp_path
        session['pdf_ocorrencias'] = ocorrencias

        return render_template("preview_pdf.html", ocorrencias=ocorrencias, pdf_data=pdf_b64)

    return render_template('tarjar_pdf.html', padroes=PADROES_SENSIVEIS.keys())

@app.route('/aplicar_tarjas_pdf', methods=['POST'])
def aplicar_tarjas_pdf_route():
    selecionados = request.form.getlist('selecionados')
    preservar_logo = request.form.get('preservar_logo', '0') == '1'
    trechos_manuais_raw = request.form.get('tarjas_manualmente_adicionadas', '')
    trechos_manuais = [t.strip() for t in trechos_manuais_raw.split('|') if t.strip()]

    caminho = session.get('pdf_path')
    ocorrencias = session.get('pdf_ocorrencias', [])

    if not caminho or not os.path.exists(caminho):
        return "Erro: arquivo temporário não encontrado.", 400

    mem_file = aplicar_tarjas_pdf(caminho, ocorrencias, selecionados, trechos_manuais, preservar_logo)

    return send_file(
        mem_file,
        as_attachment=True,
        download_name="documento_tarjado.pdf",
        mimetype="application/pdf"
    )

@app.route('/atualizar_preview_pdf', methods=['POST'])
def atualizar_preview_pdf_route():
    try:
        data = request.get_json(force=True)
        selecionados = data.get("selecionados", [])
        trechos_manuais = data.get("manuais", [])

        caminho = session.get('pdf_path')
        ocorrencias = session.get('pdf_ocorrencias', [])

        if not caminho or not os.path.exists(caminho):
            return jsonify({"erro": "Arquivo temporário não encontrado."}), 400

        pdf_b64 = atualizar_preview_pdf(caminho, ocorrencias, selecionados, trechos_manuais)
        return jsonify({"pdf_data": pdf_b64})

    except Exception as e:
        return jsonify({"erro": f"Erro no servidor: {str(e)}"}), 500

# ----------------------------------------------------------------------------------- Padrões para PDF OCR ----------------------------------------------------------------------------------

@app.route('/tarjar_ocr_pdf', methods=['GET', 'POST'])
def tarjar_ocr_pdf():
    if request.method == 'POST':
        pdf_b64, ocorrencias = OcrPdfService.processar_ocr_pdf(request, app, PADROES_SENSIVEIS, session)
        return render_template("preview_ocr.html", ocorrencias=ocorrencias, pdf_b64=pdf_b64)
    return render_template('tarjar_ocr_pdf.html', padroes=PADROES_SENSIVEIS.keys())

@app.route('/aplicar_tarjas_ocr_pdf', methods=['POST'])
def aplicar_tarjas_ocr_pdf():
    buffer, erro_msg, status = OcrPdfService.aplicar_tarjas(request, session)
    if erro_msg:
        return erro_msg, status
    return send_file(buffer, as_attachment=True, download_name="documento_tarjado.pdf", mimetype="application/pdf")

@app.route('/atualizar_preview_ocr_pdf', methods=['POST'])
def atualizar_preview_ocr_pdf():
    data, status = OcrPdfService.atualizar_preview(request, session)
    return jsonify(data), status

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