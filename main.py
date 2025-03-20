import streamlit as st
import requests
import spacy
import pdfplumber
from docx import Document
import io
import pandas as pd  

@st.cache_resource
def load_nlp_model():
    return spacy.load("en_ner_bc5cdr_md")

nlp = load_nlp_model()

UMLS_API_KEY = "838e605a-011c-4323-b50a-9112d494be99"
UMLS_BASE_URL = "https://uts-ws.nlm.nih.gov/rest"

def extract_medical_conditions(text):
    doc = nlp(text)
    return list(set(ent.text for ent in doc.ents if ent.label_ in ["DISEASE", "DISORDER"]))

def get_cui(condition):
    search_url = f"{UMLS_BASE_URL}/search/current?string={condition}&apiKey={UMLS_API_KEY}"
    response = requests.get(search_url)

    if response.status_code == 200:
        results = response.json().get("result", {}).get("results", [])
        for item in results:
            if item["ui"] != "NONE":
                return item["ui"]
    return None

def get_icd10_from_cui(cui):
    icd10_codes = set()
    atoms_url = f"{UMLS_BASE_URL}/content/current/CUI/{cui}/atoms?sabs=ICD10CM&apiKey={UMLS_API_KEY}"
    response_atoms = requests.get(atoms_url)

    if response_atoms.status_code == 200:
        for item in response_atoms.json().get("result", []):
            icd_code = item.get("code")
            name = item.get("name")
            if icd_code:
                icd10_codes.add((icd_code.split("/")[-1], name))

    return list(icd10_codes) if icd10_codes else None

def extract_text_from_file(uploaded_file):
    file_type = uploaded_file.type

    if "text" in file_type:
        return uploaded_file.read().decode("utf-8")
    elif "pdf" in file_type:
        text = ""
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
        return text
    elif "word" in file_type or "msword" in file_type:
        doc = Document(io.BytesIO(uploaded_file.read()))
        return "\n".join([para.text for para in doc.paragraphs])

    return None

st.title("MedExtract ICD")
st.markdown("Upload a file or enter a doctor's note to extract medical conditions and map them to ICD-10 codes.")

option = st.radio("Choose input method:", ["Enter Text", "Upload File"])

user_input = ""
if option == "Enter Text":
    user_input = st.text_area("Doctor's Note", "")

elif option == "Upload File":
    uploaded_file = st.file_uploader("Upload a text, PDF, or DOCX file", type=["txt", "pdf", "docx"])

    if uploaded_file:
        user_input = extract_text_from_file(uploaded_file)
        st.text_area("Extracted Text", user_input, height=200)

# Initialize session state for extracted data
if "extracted_data" not in st.session_state:
    st.session_state.extracted_data = []
if "display_data" not in st.session_state:
    st.session_state.display_data = []

if st.button("Extract & Map"):
    if user_input and user_input.strip():
        with st.spinner("Processing..."):
            conditions = extract_medical_conditions(user_input)

            if conditions:
                data_list = []
                display_list = []
                for condition in conditions:
                    cui = get_cui(condition)
                    if cui:
                        icd10_codes = get_icd10_from_cui(cui)
                        if icd10_codes:
                            for icd_code, name in icd10_codes:
                                display_list.append(f"✅ **{condition}** ➝ ICD-10: **{icd_code}** ({name})")
                                data_list.append([condition, icd_code, name])
                        else:
                            display_list.append(f"⚠️ **{condition}** ➝ No ICD-10 code found.")
                            data_list.append([condition, "No ICD-10 Code Found", ""])
                    else:
                        display_list.append(f"⚠️ **{condition}** ➝ No CUI found.")
                        data_list.append([condition, "No CUI Found", ""])

                st.session_state.extracted_data = data_list
                st.session_state.display_data = display_list

            else:
                st.warning("No medical conditions detected.")
    else:
        st.error("Please enter a doctor's note or upload a file.")

# Display extracted data (this persists across dropdown selection)
if st.session_state.display_data:
    st.subheader("Extracted Medical Conditions and Mappings:")
    for item in st.session_state.display_data:
        st.write(item)

if st.session_state.extracted_data:
    st.subheader("Download Extracted Data")
    file_format = st.selectbox("Select file format:", ["CSV", "TXT", "JSON"])

    df = pd.DataFrame(st.session_state.extracted_data, columns=["Medical Condition", "ICD-10 Code", "Description"])

    if file_format == "CSV":
        download_data = df.to_csv(index=False).encode("utf-8")
        file_ext = "csv"
        mime_type = "text/csv"
    elif file_format == "TXT":
        download_data = "\n".join([f"{row[0]} -> {row[1]} ({row[2]})" for row in st.session_state.extracted_data]).encode("utf-8")
        file_ext = "txt"
        mime_type = "text/plain"
    elif file_format == "JSON":
        download_data = df.to_json(orient="records", indent=4).encode("utf-8")
        file_ext = "json"
        mime_type = "application/json"

    st.download_button(
        label="Download File",
        data=download_data,
        file_name=f"medical_conditions.{file_ext}",
        mime=mime_type,
    )
