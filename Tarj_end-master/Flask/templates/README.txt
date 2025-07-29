import os
import re
import glob

import fitz
import pandas as pd
from datetime import datetime
from tkinter import Tk, Toplevel, Text, Scrollbar, Label, Button, filedialog, messagebox, RIGHT, Y, END, Toplevel,  Checkbutton, IntVar, scrolledtext
from tkinter import ttk
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
from docx import Document



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
}



# ------------------- TARJAMENTO PDF --------------------

def selecionar_padroes():
    padroes_escolhidos = {}

    def confirmar():
        for chave, var in check_vars.items():
            if var.get():
                padroes_escolhidos[chave] = padroes[chave]
        janela.destroy()

    janela = Toplevel()
    janela.title("Selecionar Dados a Tarjar")
    Label(janela, text="Escolha quais dados devem ser tarjados:", font=("Arial", 10, "bold")).pack(pady=10)

    check_vars = {}
    for chave in padroes:
        var = tk.IntVar(value=1)  # Todos marcados por padrão
        chk = tk.Checkbutton(janela, text=chave, variable=var)
        chk.pack(anchor="w")
        check_vars[chave] = var

    Button(janela, text="Confirmar", command=confirmar).pack(pady=10)
    janela.wait_window()

    return padroes_escolhidos




def tarjar_pdf_seletivo():
    caminho = filedialog.askopenfilename(title="Selecione um PDF", filetypes=[("PDF", "*.pdf")])
    if not caminho:
        return

    try:
        doc = fitz.open(caminho)
    except Exception as e:
        messagebox.showerror("Erro", f"Erro ao abrir o PDF:\n{e}")
        return

    if doc.page_count == 0:
        messagebox.showwarning("PDF Vazio", "O PDF não tem páginas.")
        doc.close()
        return

    padroes_escolhidos = selecionar_padroes()
    if not padroes_escolhidos:
        messagebox.showinfo("Cancelado", "Nenhum padrão selecionado.")
        doc.close()
        return

    ocorrencias = []  

    
    for page_num, page in enumerate(doc):
        texto = page.get_text()
        for tipo, padrao in padroes_escolhidos.items():
            for match in re.finditer(padrao, texto, re.IGNORECASE):
                encontrado = match.group()
                areas = page.search_for(encontrado)
                for area in areas:
                    var = IntVar(value=1)
                    ocorrencias.append((page_num, encontrado, area, var))

    if not ocorrencias:
        messagebox.showinfo("Nada Encontrado", "Nenhum dado sensível encontrado.")
        doc.close()
        return

    
    def aplicar_tarjas2():
        for page_num, texto, area, var in ocorrencias:
            if var.get():
                page = doc[page_num]
                page.add_redact_annot(area, fill=(0, 0, 0))

# 2. Aplica a redaction (remove texto original e aplica tarja)
                page.apply_redactions()

        novo_nome = caminho.replace(".pdf", "_TARJADO.pdf")
        doc.save(novo_nome)
        messagebox.showinfo("Sucesso", f"PDF salvo como:\n{novo_nome}")
        doc.close()
        janela.destroy()

    janela = Toplevel()
    janela.title("Escolha o que deseja tarjar")

    for i, (page_num, texto, area, var) in enumerate(ocorrencias):
        Checkbutton(
            janela,
            text=f"Página {page_num + 1}: {texto}",
            variable=var,
            anchor="w",
            width=60,
            justify="left"
        ).pack(anchor="w")

    Button(janela, text="Aplicar Tarjas", command=aplicar_tarjas2, bg="black", fg="white").pack(pady=10)
    Button(janela, text="Cancelar", command=lambda: (doc.close(), janela.destroy())).pack()