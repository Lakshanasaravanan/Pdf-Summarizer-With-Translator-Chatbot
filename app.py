import streamlit as st
import fitz
from groq import Groq
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from datetime import datetime
from deep_translator import GoogleTranslator
import re


# PAGE CONFIG
st.set_page_config(page_title="PDF Summarizer & Translator Chatbot", page_icon="📚", layout="wide")


# STYLES
st.markdown("""
<style>
html, body, .stApp { background: #1F2232; margin:0; padding:0;}
.block-container { padding-top: 2.5rem; padding-bottom: 2.5rem; }
h1, h2, h3, h4 { color: #43C6AC; font-weight: 700;}
.main-title { font-size:2.5rem; display:flex; align-items:center; gap:0.5rem;
              color:#ebf4fa; font-family: 'Poppins', sans-serif; font-weight:800;}
.section-title { color:#43C6AC; margin-bottom:1.2rem;}
.stButton>button { background: linear-gradient(90deg,#43C6AC 0,#191654 100%);
                   color: white; border: none; border-radius: 8px;
                   padding: .65rem 1.7rem; font-weight: 700; font-size:1rem;}
.stButton>button:hover { filter:brightness(1.10);}
.stFileUploader { background:#232946 !important; border-radius:10px; }
.stTextInput>div>div>input { background: #232946 !important; color: #E3E3E3 !important;}
.chat-bubble { padding:1.05rem; margin:.7rem 0; border-radius:13px; font-size:1.11rem;}
.user-bubble { background: linear-gradient(90deg,#43C6AC 0,#191654 100%); color:white; margin-left:80px;}
.bot-bubble { background:#cdcfff; color:#171b2b;margin-right:80px;}
.stDownloadButton>button { background:linear-gradient(90deg,#43C6AC 0,#191654 100%);
                           border-radius:8px; color:white; font-weight:600;}
.sidebar-content { color:#eee; font-size: 1.09rem;}
hr { border-top: 1.5px solid #2e4466; }
</style>
""", unsafe_allow_html=True)


# SESSION
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'pdf_data' not in st.session_state:
    st.session_state.pdf_data = {}
if 'summaries' not in st.session_state:
    st.session_state.summaries = {}
if 'translated_output' not in st.session_state:
    st.session_state.translated_output = {}


# FUNCTIONS
def extract_pdf_text(pdf_file):
    """Extract ALL pages from PDF"""
    doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
    pages = {page_num + 1: doc[page_num].get_text() for page_num in range(len(doc))}
    return pages


def extract_page_number(query):
    """Check if user is asking about a specific page"""
    patterns = [
        r'page\s*(?:no|number|#)?\s*(\d+)',
        r'(\d+)\s*(?:st|nd|rd|th)?\s*page',
        r'on\s*page\s*(\d+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, query.lower())
        if match:
            return int(match.group(1))
    return None


def get_relevant_context(query, pdf_data, max_chars=7000):
    """Get relevant context based on query"""
    page_num = extract_page_number(query)
    if page_num:
        for fname, pages in pdf_data.items():
            if page_num in pages:
                return f"[{fname} - Page {page_num}]\n{pages[page_num]}", [page_num]
        return "Page not found in the uploaded PDF.", []
    
    context_parts = []
    total_chars = 0
    pages_used = []
    for fname, pages in pdf_data.items():
        total_pages = len(pages)
        sample_interval = max(1, total_pages // 10)
        for page_num in range(1, total_pages + 1, sample_interval):
            if page_num in pages:
                page_text = pages[page_num][:700]
                if total_chars + len(page_text) < max_chars:
                    context_parts.append(f"[{fname} - Page {page_num}] {page_text}")
                    total_chars += len(page_text)
                    pages_used.append(page_num)
                else:
                    break
    return "\n\n".join(context_parts), pages_used


def export_to_pdf(content, content_type="chat"):
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    base_font = 'Helvetica'
    
    title_style = ParagraphStyle('SectionTitle', parent=styles['Heading1'], alignment=TA_CENTER, 
                                 spaceAfter=20, fontSize=20, fontName=base_font)
    normal_style = ParagraphStyle('Body', parent=styles['Normal'], spaceAfter=10, alignment=TA_JUSTIFY,
                                  leading=16, fontSize=12, fontName=base_font)
    file_style = ParagraphStyle('FileTitle', parent=styles['Heading2'], spaceAfter=16, 
                               textColor="#191654", fontName=base_font)
    user_style = ParagraphStyle('UserStyle', parent=styles['Heading3'], spaceAfter=8, 
                               textColor="#1a4a80", fontSize=13, fontName=base_font)
    bot_style = ParagraphStyle('BotStyle', parent=styles['BodyText'], backColor="#F1F5FC", borderWidth=1,
                              borderPadding=(8, 8, 8), leading=16, textColor="#16263a",
                              fontSize=12, spaceAfter=18, leftIndent=16, fontName=base_font)

    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=1*inch, rightMargin=1*inch,
                            topMargin=1*inch, bottomMargin=1*inch)
    story = []
    story.append(Paragraph("PDF Summarizer & Translator Chatbot", title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
    story.append(Spacer(1, 0.2*inch))

    if content_type == "chat":
        story.append(Paragraph("Chat Transcript", file_style))
        for msg in content:
            role = "You:" if msg["role"] == "user" else "Bot:"
            story.append(Paragraph(role, user_style))
            safe = msg["content"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe.replace("\n", "<br/>"), normal_style if msg["role"]=="user" else bot_style))
    
    elif content_type == "summary":
        story.append(Paragraph("PDF Summaries", file_style))
        for filename, summary in content.items():
            story.append(Paragraph(filename, file_style))
            safe = summary.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe.replace("\n", "<br/>"), normal_style))
            story.append(PageBreak())

    doc.build(story)
    buffer.seek(0)
    return buffer


def export_translation_txt(content):
    """Export translations as plain text file"""
    output = f"PDF Summarizer & Translator Chatbot\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    output += "="*60 + "\nTranslated PDF Content\n" + "="*60 + "\n\n"
    for filename, pages in content.items():
        output += f"\n{'='*60}\nFile: {filename}\n{'='*60}\n\n"
        for page_num, text in pages.items():
            output += f"\n--- Page {page_num} ---\n\n{text}\n\n"
    return output.encode('utf-8')


def translate_text(text, target_lang):
    if isinstance(text, list):
        text = "\n".join(text)
    result = GoogleTranslator(source='auto', target=target_lang).translate(text)
    return result


# HEADER
st.markdown("<div class='main-title'>📚 PDF Summarizer & Translator Chatbot</div>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)


# SIDEBAR
with st.sidebar:
    st.markdown("<span class='sidebar-content'><b>⚙️ Configuration</b></span>", unsafe_allow_html=True)
    api_key = st.text_input("Groq API Key", type="password")
    mode = st.radio("Mode", ["💬 Chat", "📝 Summary", "🌎 Translate"])
    
    if st.session_state.pdf_data:
        total_pages = sum(len(pages) for pages in st.session_state.pdf_data.values())
        st.success(f"✅ {len(st.session_state.pdf_data)} PDF(s) loaded ({total_pages} pages)")
    
    st.markdown("---")
    st.markdown("<span class='sidebar-content'><b>💾 Export Options</b></span>", unsafe_allow_html=True)
    
    if st.session_state.messages:
        st.download_button(
            "📥 Export Chat as PDF",
            data=export_to_pdf(st.session_state.messages, "chat"),
            file_name=f"Chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    
    if st.session_state.summaries:
        st.download_button(
            "📥 Export Summaries as PDF",
            data=export_to_pdf(st.session_state.summaries, "summary"),
            file_name=f"Summaries_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    
    if st.session_state.translated_output:
        st.download_button(
            "📥 Export Translations as TXT",
            data=export_translation_txt(st.session_state.translated_output),
            file_name=f"Translations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            use_container_width=True
        )
    
    st.markdown("---")
    if st.button("🗑️ Clear All", use_container_width=True):
        for key in ["messages", "pdf_data", "summaries", "translated_output"]:
            st.session_state[key] = [] if key == "messages" else {}
        st.rerun()


# PDF UPLOAD
st.subheader("Upload PDF Files")
uploaded_files = st.file_uploader("Upload PDF files", type=["pdf"], accept_multiple_files=True)


# CHAT MODE
if mode == "💬 Chat":
    st.markdown("### 💬 Chat with Your PDFs")
    
    if uploaded_files and not st.session_state.pdf_data:
        if st.button("🚀 Process PDFs"):
            progress = st.progress(0)
            for idx, pdf in enumerate(uploaded_files):
                st.session_state.pdf_data[pdf.name] = extract_pdf_text(pdf)
                progress.progress((idx + 1) / len(uploaded_files))
            st.success(f"✅ {len(uploaded_files)} PDF(s) processed successfully!")
            st.rerun()
    
    # 🔐 API key validation
    if not api_key:
        st.error("❌ Please add your Groq API key to get optimal solutions.")
    
    elif st.session_state.pdf_data:
        for msg in st.session_state.messages:
            style = "user-bubble" if msg["role"] == "user" else "bot-bubble"
            st.markdown(
                f"<div class='chat-bubble {style}'><b>{msg['role'].title()}:</b> {msg['content']}</div>", 
                unsafe_allow_html=True
            )
        
        with st.form("chat_form", clear_on_submit=True):
            user_query = st.text_input("Ask a question about your PDFs:")
            send = st.form_submit_button("Send")
        
        if send and user_query.strip():
            query = user_query.strip()
            st.session_state.messages.append({"role": "user", "content": query})
            
            with st.spinner("🤔 Thinking..."):
                context, pages_used = get_relevant_context(query, st.session_state.pdf_data)
                
                try:
                    response = Groq(api_key=api_key).chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {"role": "system", "content": f"Use this PDF content to answer:\n{context}"},
                            {"role": "user", "content": query}
                        ],
                        temperature=0.3,
                        max_tokens=1500
                    )
                    answer = response.choices[0].message.content
                    if pages_used:
                        answer += f"\n\n*Referenced pages: {', '.join(map(str, pages_used))}*"
                    st.session_state.messages.append({"role": "assistant", "content": answer})
                except Exception as e:
                    st.error(f"Error: {str(e)}")
            st.rerun()


# SUMMARY MODE
elif mode == "📝 Summary":
    st.markdown("### 📝 Generate Summaries")
    
    if uploaded_files and not st.session_state.pdf_data:
        if st.button("🚀 Process PDFs"):
            progress = st.progress(0)
            for idx, pdf in enumerate(uploaded_files):
                st.session_state.pdf_data[pdf.name] = extract_pdf_text(pdf)
                progress.progress((idx + 1) / len(uploaded_files))
            st.success(f"✅ {len(uploaded_files)} PDF(s) processed successfully!")
            st.rerun()
    
    # 🔐 API key validation
    if not api_key:
        st.error("❌ Please add your Groq API key to get optimal solutions.")
    
    elif st.session_state.pdf_data:
        if st.button("🎯 Generate Summaries"):
            progress_bar = st.progress(0)
            total_files = len(st.session_state.pdf_data)
            
            with st.spinner("Generating detailed summaries..."):
                for idx, (fname, pages) in enumerate(st.session_state.pdf_data.items()):
                    sampled_text = ""
                    total_pages = len(pages)
                    sample_interval = max(1, total_pages // 20)
                    for page_num in range(1, total_pages + 1, sample_interval):
                        if page_num in pages:
                            sampled_text += pages[page_num][:400] + "\n"
                    sampled_text = sampled_text[:7000]
                    
                    try:
                        response = Groq(api_key=api_key).chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=[
                                {"role": "system", "content": f"Provide a comprehensive summary covering key points from this {total_pages}-page document."},
                                {"role": "user", "content": sampled_text}
                            ],
                            temperature=0.5,
                            max_tokens=1500
                        )
                        st.session_state.summaries[fname] = response.choices[0].message.content
                    except Exception as e:
                        st.session_state.summaries[fname] = f"Error: {str(e)}"
                    progress_bar.progress((idx + 1) / total_files)
                
                st.success("✅ Summaries generated!")
                st.rerun()
        
        if st.session_state.summaries:
            for fname, summary in st.session_state.summaries.items():
                with st.expander(f"📘 {fname}", expanded=True):
                    st.markdown(
                        f"<div class='chat-bubble bot-bubble'><h4>Summary</h4><p>{summary}</p></div>", 
                        unsafe_allow_html=True
                    )


# TRANSLATE MODE
elif mode == "🌎 Translate":
    st.markdown("### 🌍 Translate PDF Content")
    
    if uploaded_files and not st.session_state.pdf_data:
        if st.button("🚀 Process PDFs"):
            progress = st.progress(0)
            for idx, pdf in enumerate(uploaded_files):
                st.session_state.pdf_data[pdf.name] = extract_pdf_text(pdf)
                progress.progress((idx + 1) / len(uploaded_files))
            st.success(f"✅ {len(uploaded_files)} PDF(s) processed successfully!")
            st.rerun()
    
    # 🔐 API key validation
    if not api_key:
        st.error("❌ Please add your Groq API key to get optimal solutions.")
    
    elif st.session_state.pdf_data:
        languages = {
            "English (en)": "en", "Tamil (ta)": "ta", "Hindi (hi)": "hi", "Spanish (es)": "es",
            "French (fr)": "fr", "German (de)": "de", "Chinese (zh)": "zh", "Arabic (ar)": "ar",
            "Russian (ru)": "ru", "Portuguese (pt)": "pt", "Japanese (ja)": "ja",
            "Korean (ko)": "ko", "Italian (it)": "it"
        }

        st.markdown(
            "<div style='color:#E3E3E3;font-size:1.1rem;margin-top:0.5rem;'>Select a language:</div>",
            unsafe_allow_html=True
        )
        chosen_lang = st.selectbox("", list(languages.keys()))
        lang_code = languages[chosen_lang]

        if st.button("🌐 Translate PDFs"):
            translated_data = {}
            progress_bar = st.progress(0)
            total_files = len(st.session_state.pdf_data)
            
            with st.spinner(f"Translating to {chosen_lang}..."):
                for idx, (fname, pages) in enumerate(st.session_state.pdf_data.items()):
                    translated_pages = {}
                    for pageno, text in pages.items():
                        if text.strip():
                            try:
                                translation = translate_text(text, lang_code)
                                translated_pages[pageno] = translation
                            except Exception as e:
                                translated_pages[pageno] = f"[Error: {str(e)}]"
                        else:
                            translated_pages[pageno] = "[Empty]"
                    translated_data[fname] = translated_pages
                    progress_bar.progress((idx + 1) / total_files)
                
                st.session_state.translated_output = translated_data
                st.success("✅ Translation Completed!")
                st.rerun()

        if st.session_state.translated_output:
            st.markdown("<hr>", unsafe_allow_html=True)
            st.markdown("<h4 style='color:#43C6AC;'>📖 Translated Output</h4>", unsafe_allow_html=True)

            for fname, pages in st.session_state.translated_output.items():
                with st.expander(f"📄 {fname}", expanded=False):
                    for pageno, translated_text in pages.items():
                        st.markdown(
                            f"<div class='chat-bubble bot-bubble'><b>Page {pageno}</b><br>{translated_text}</div>",
                            unsafe_allow_html=True
                        )


# FOOTER
st.markdown(
    "<div style='text-align:center; color:#93E1D8; padding:1rem; font-size:1.07rem;'>"
    "Built with ❤️ using Groq AI, Deep Translator & Streamlit"
    "</div>", 
    unsafe_allow_html=True
)
