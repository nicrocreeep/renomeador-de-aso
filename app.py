import streamlit as st
import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image, ImageEnhance, ImageOps
import re
import io
import zipfile

st.set_page_config(page_title="Renomeador de ASO por Código", page_icon="📄", layout="wide")

st.title("📄 Renomeador Automático de ASO e Verificador de Assinatura")

def extract_aso_code(text):
    if not text:
        return None

    clean_text = re.sub(r'\s+', '', text)

    # Busca padrão: M + caracteres + E + 8 dígitos + V + 8 dígitos
    match = re.search(r'(M[A-Za-z0-9]+?E\d{8}V\d{8})', clean_text, re.IGNORECASE)
    if match:
        return match.group(1).upper()

    match_fallback = re.search(r'(M[A-Za-z0-9]{5,25}E\d{8})', clean_text, re.IGNORECASE)
    if match_fallback:
        return match_fallback.group(1).upper()

    return None

def check_signature_status(doc, full_text):
    """
    Verifica se o ASO possui assinatura válida (DocuSign com Certificado ou Assinatura Física/Carimbo)
    """
    text_lower = full_text.lower()

    # 1. Verificação DocuSign
    if "docusign" in text_lower:
        has_certificate = ("certificado de conclusão" in text_lower) or ("certificate of completion" in text_lower)
        if has_certificate:
            return "✅ DocuSign (Com Certificado)", True
        else:
            return "❌ DocuSign Inválido (Sem Certificado)", False

    # 2. Verificação Assinatura Física / Carimbo (Análise de Imagem no Campo Médico)
    try:
        page = doc[0]
        rects = page.search_for("Carimbo e Assinatura") or page.search_for("Médico Examinador")
        
        if rects:
            r = rects[0]
            # Bounding box ao redor e acima da linha de assinatura
            sig_rect = fitz.Rect(r.x0 - 60, r.y0 - 130, r.x1 + 160, r.y0 + 20)
        else:
            # Região padrão da assinatura do médico (canto inferior direito)
            p_rect = page.rect
            sig_rect = fitz.Rect(p_rect.width * 0.35, p_rect.height * 0.55, p_rect.width * 0.95, p_rect.height * 0.82)

        # Captura imagens na página (se for escaneado ou tiver carimbo/imagem colada)
        images = page.get_images()

        # Renderiza a área da assinatura para verificar densidade de tinta/desenho
        pix = page.get_pixmap(clip=sig_rect, dpi=150)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")

        # Binarização (Preto e Branco)
        threshold = 200
        bw_img = img.point(lambda p: 255 if p > threshold else 0)
        black_pixels = bw_img.histogram()[0]
        total_pixels = img.width * img.height
        black_ratio = black_pixels / total_pixels

        # Se houver densidade de tinta no campo ou imagem embutida na página
        if black_ratio > 0.035 or len(images) > 0:
            return "✅ Assinado (Físico / Carimbo)", True
        else:
            return "⚠️ Sem Assinatura (Em Branco)", False

    except Exception:
        return "❓ Verificação Manual Necessária", False

def process_pdf(file_bytes):
    aso_code = None
    full_text = ""
    doc = None

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page in doc:
            full_text += page.get_text("text") + " "
        aso_code = extract_aso_code(full_text)
    except Exception:
        pass

    # Leitura alternativa via pdfplumber
    if not aso_code:
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                full_text = ""
                for page in pdf.pages:
                    full_text += (page.extract_text() or "") + " "
                aso_code = extract_aso_code(full_text)
        except Exception:
            pass

    # Fallback OCR para escaneados
    if not aso_code and doc:
        try:
            ocr_text = ""
            for page in doc:
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                
                width, height = img.size
                crop_box = (0, int(height * 0.75), width, height)
                footer_img = img.crop(crop_box)
                
                gray = ImageOps.grayscale(footer_img)
                enhancer = ImageEnhance.Contrast(gray)
                processed_img = enhancer.enhance(2.0)
                
                ocr_text += pytesseract.image_to_string(processed_img, config='--psm 6') + " "
            
            aso_code = extract_aso_code(ocr_text)
            full_text += " " + ocr_text
        except Exception:
            pass

    # Validação da Assinatura
    sig_status, is_valid_sig = check_signature_status(doc, full_text) if doc else ("❓ Erro na Leitura", False)

    return aso_code, sig_status, is_valid_sig

uploaded_files = st.file_uploader(
    "Envie seus arquivos de ASO em PDF (pode selecionar todos de uma vez):",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    st.info(f"Total de arquivos carregados: **{len(uploaded_files)}**")
    
    if st.button("🚀 Processar, Verificar Assinatura e Renomear"):
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for idx, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"Processando [{idx+1}/{len(uploaded_files)}]: {uploaded_file.name}")
                
                file_bytes = uploaded_file.read()
                aso_code, sig_status, is_valid_sig = process_pdf(file_bytes)
                
                original_name = uploaded_file.name
                base_name = original_name[:-4] if original_name.lower().endswith(".pdf") else original_name
                
                # Definição do novo nome e status
                if aso_code and is_valid_sig:
                    new_filename = f"{aso_code}.pdf"
                    final_status = "✅ Prontos para Benner"
                elif aso_code and not is_valid_sig:
                    new_filename = f"{aso_code} - REJEITADO_ASSINATURA.pdf"
                    final_status = "⚠️ Falha de Assinatura"
                else:
                    new_filename = f"{base_name} - CODIGO_NAO_ENCONTRADO.pdf"
                    final_status = "⚠️ Código não localizado"
                
                zip_file.writestr(new_filename, file_bytes)
                
                results.append({
                    "Arquivo Original": original_name,
                    "Código Extraído": aso_code if aso_code else "Não localizado",
                    "Validação de Assinatura": sig_status,
                    "Novo Nome do Arquivo": new_filename,
                    "Status Final": final_status
                })
                
                progress_bar.progress((idx + 1) / len(uploaded_files))
        
        status_text.text("✨ Processamento concluído!")
        
        st.subheader("📋 Resumo da Análise dos ASOs")
        st.dataframe(results, use_container_width=True)
        
        zip_buffer.seek(0)
        st.download_button(
            label="📦 Baixar Todos os Arquivos Renomeados (.ZIP)",
            data=zip_buffer,
            file_name="ASOs_Processados.zip",
            mime="application/zip"
        )
