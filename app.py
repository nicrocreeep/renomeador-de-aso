import streamlit as st
import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image
import re
import io
import zipfile

st.set_page_config(page_title="Renomeador de ASO por Código", page_icon="📄", layout="wide")

st.title("📄 Renomeador Automático de ASO pelo Código de Controle")
st.markdown("""
Esta aplicação analisa os arquivos de **ASO (Atestado de Saúde Ocupacional)**, localiza a tag do código de controle no rodapé e **renomeia o arquivo para o código começando por M** (sem o `#`).

**Exemplo:**
- Tag no ASO: `#M90468C1P3D3E03092026V03092027`
- Código Extraído: `M90468C1P3D3E03092026`
- **Novo Nome do Arquivo:** `M90468C1P3D3E03092026.pdf`
""")

def extract_aso_code(text):
    if not text:
        return None

    # Captura a partir da letra 'M' até os 8 dígitos da data de emissão (após o 'E'), ignorando o '#'
    # Exemplo: '#M90468C1P3D3E03092026V03092027' -> Extrai 'M90468C1P3D3E03092026'
    match = re.search(r'#?(M\w+?E\d{8})V?', text)
    if match:
        return match.group(1)

    return None

def process_pdf(file_bytes):
    # 1. Leitura rápida de texto nativo via PyMuPDF
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        
        found_code = extract_aso_code(text)
        if found_code:
            return found_code
    except Exception:
        pass

    # 2. Leitura via pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
            
            found_code = extract_aso_code(text)
            if found_code:
                return found_code
    except Exception:
        pass

    # 3. Fallback OCR (pytesseract) para ASOs escaneados
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page in doc:
            pix = page.get_pixmap(dpi=150)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text += pytesseract.image_to_string(img) + "\n"
        
        found_code = extract_aso_code(text)
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
