import streamlit as st
import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image
import re
import io
import zipfile

st.set_page_config(page_title="Renomeador de ASO por Código", page_icon="📄", layout="wide")

st.title("📄 Renomeador Automático de ASO por Código de Emissão")
st.markdown("""
Esta aplicação analisa os arquivos de **ASO (Atestado de Saúde Ocupacional)**, extrai a data de emissão contida na estrutura do código `#M...E[DDMMAAAA]` do rodapé e renomeia o arquivo adicionando a data formatada no final.

**Estrutura do Código:**
- `#M[MATRÍCULA]C[EMPRESA]P[PROCESSO]D[TIPO]E[DATA_EMISSÃO]V[DATA_VALIDADE]`
- Exemplo: `#M90468C1P3D3E03092026V03092027` ➔ Extrai **03.09.2026**
""")

def extract_emission_date_from_code(text):
    if not text:
        return None

    # Captura a data de 8 dígitos que vem exatamente após 'E' no padrão #M...
    # Exemplo: #M90468C1P3D3E03092026V03092027
    match = re.search(r'#M\w+?E(\d{2})(\d{2})(\d{4})', text)
    if match:
        day, month, year = match.groups()
        return f"{day}.{month}.{year}"

    # Fallback caso a hashtag #M não venha completa no OCR, mas venha E[DDMMAAAA]V
    match_fallback = re.search(r'E(\d{2})(\d{2})(\d{4})V', text)
    if match_fallback:
        day, month, year = match_fallback.groups()
        return f"{day}.{month}.{year}"

    return None

def process_pdf(file_bytes):
    # 1. Leitura rápida do texto nativo via PyMuPDF
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        
        extracted_date = extract_emission_date_from_code(text)
        if extracted_date:
            return extracted_date
    except Exception:
        pass

    # 2. Leitura via pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
            
            extracted_date = extract_emission_date_from_code(text)
            if extracted_date:
                return extracted_date
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
        
        extracted_date = extract_emission_date_from_code(text)
        if extracted_date:
            return extracted_date
    except Exception:
        pass

    return None

uploaded_files = st.file_uploader(
    "Envie seus arquivos de ASO em PDF (pode selecionar os 55 arquivos de uma vez):",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    st.info(f"Total de arquivos carregados: **{len(uploaded_files)}**")
    
    if st.button("🚀 Processar e Renomear Arquivos"):
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for idx, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"Processando [{idx+1}/{len(uploaded_files)}]: {uploaded_file.name}")
                
                file_bytes = uploaded_file.read()
                found_date = process_pdf(file_bytes)
                
                original_name = uploaded_file.name
                base_name = original_name[:-4] if original_name.lower().endswith(".pdf") else original_name
                
                if found_date:
                    new_filename = f"{base_name} - {found_date}.pdf"
                    status = "✅ Sucesso"
                else:
                    new_filename = f"{base_name} - CODIGO_NAO_ENCONTRADO.pdf"
                    status = "⚠️ Código não localizado"
                
                zip_file.writestr(new_filename, file_bytes)
                
                results.append({
                    "Arquivo Original": original_name,
                    "Data Emissão (E)": found_date if found_date else "Não localizada",
                    "Novo Nome": new_filename,
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