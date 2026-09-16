import streamlit as st
import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image, ImageEnhance, ImageOps
import re
import io
import zipfile

st.set_page_config(page_title="Renomeador de ASO por Código", page_icon="📄", layout="wide")

st.title("📄 Renomeador Automático de ASO pelo Código de Controle")

def extract_aso_code(text):
    if not text:
        return None

    # Remove quebras de linha e múltiplos espaços para garantir que a tag fique contínua
    clean_text = re.sub(r'\s+', '', text)

    # Busca o padrão: M + caracteres + E + 8 dígitos + V + 8 dígitos
    # Exemplo extraído: M65614C1P3D3E01122025V01122026
    match = re.search(r'(M[A-Za-z0-9]+?E\d{8}V\d{8})', clean_text, re.IGNORECASE)
    if match:
        return match.group(1).upper()

    # Fallback mais permissivo caso falhar a data de vencimento
    match_fallback = re.search(r'(M[A-Za-z0-9]{5,25}E\d{8})', clean_text, re.IGNORECASE)
    if match_fallback:
        return match_fallback.group(1).upper()

    return None

def process_pdf(file_bytes):
    # 1. Leitura rápida de texto nativo via PyMuPDF (Lê bloco a bloco)
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        full_text = ""
        for page in doc:
            full_text += page.get_text("text") + " "
        
        found_code = extract_aso_code(full_text)
        if found_code:
            return found_code
    except Exception:
        pass

    # 2. Leitura via pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += (page.extract_text() or "") + " "
            
            found_code = extract_aso_code(full_text)
            if found_code:
                return found_code
    except Exception:
        pass

    # 3. Fallback OCR focado no Rodapé (Recorte dos últimos 20% da página)
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        full_text = ""
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            
            # Recorta apenas o rodapé (últimos 20% de altura) para focar na tag
            width, height = img.size
            crop_box = (0, int(height * 0.75), width, height)
            footer_img = img.crop(crop_box)
            
            # Tratamento de imagem para OCR
            gray = ImageOps.grayscale(footer_img)
            enhancer = ImageEnhance.Contrast(gray)
            processed_img = enhancer.enhance(2.0)
            
            full_text += pytesseract.image_to_string(processed_img, config='--psm 6') + " "
            full_text += pytesseract.image_to_string(processed_img) + " "
        
        found_code = extract_aso_code(full_text)
        if found_code:
            return found_code
    except Exception:
        pass

    return None

uploaded_files = st.file_uploader(
    "Envie seus arquivos de ASO em PDF (pode selecionar todos de uma vez):",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    st.info(f"Total de arquivos carregados: **{len(uploaded_files)}**")
    
    if st.button("🚀 Processar e Renomear para o Código"):
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for idx, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"Processando [{idx+1}/{len(uploaded_files)}]: {uploaded_file.name}")
                
                file_bytes = uploaded_file.read()
                aso_code = process_pdf(file_bytes)
                
                original_name = uploaded_file.name
                
                if aso_code:
                    new_filename = f"{aso_code}.pdf"
                    status = "✅ Sucesso"
                else:
                    base_name = original_name[:-4] if original_name.lower().endswith(".pdf") else original_name
                    new_filename = f"{base_name} - CODIGO_NAO_ENCONTRADO.pdf"
                    status = "⚠️ Código não localizado"
                
                zip_file.writestr(new_filename, file_bytes)
                
                results.append({
                    "Arquivo Original": original_name,
                    "Código Extraído": aso_code if aso_code else "Não localizado",
                    "Novo Nome do Arquivo": new_filename,
                    "Status": status
                })
                
                progress_bar.progress((idx + 1) / len(uploaded_files))
        
        status_text.text("✨ Processamento concluído!")
        
        st.subheader("📋 Resumo do Processamento")
        st.dataframe(results, use_container_width=True)
        
        zip_buffer.seek(0)
        st.download_button(
            label="📦 Baixar Todos os Arquivos Renomeados (.ZIP)",
            data=zip_buffer,
            file_name="ASOs_Renomeados.zip",
            mime="application/zip"
        )
