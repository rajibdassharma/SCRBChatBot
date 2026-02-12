import tempfile
import os
from pathlib import Path
from random import randrange
import StartChat3

import streamlit as st
from streamlit_option_menu import option_menu

from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.chat_models import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain.document_loaders.csv_loader import CSVLoader
from langchain.document_loaders import PyPDFLoader
from langchain.document_loaders import TextLoader
from langchain.vectorstores import FAISS
from langchain.document_loaders import DirectoryLoader
from langchain.text_splitter import CharacterTextSplitter

from streamlit_chat import message
from src.styles.menu_styles import FOOTER_STYLES, HEADER_STYLES
from src.utils.conversation import get_user_input, show_chat_buttons, show_conversation
from src.utils.footer import show_info
from src.utils.helpers import get_files_in_dir, get_random_img
from src.utils.lang import en

from AIAgent import AIAgentSearch
from GenerateContent import generate_sm_content
from MainLogin import main_login

from secret_key import API_KEY

# Storing The Context
if "locale" not in st.session_state:
    st.session_state.locale = en
if "filesuploaded" not in st.session_state:
    st.session_state.filesuploaded = 0
if "data" not in st.session_state:
    st.session_state["data"] = []
    data = []
if "dataLoaded" not in st.session_state:
    st.session_state.dataLoaded = False

def upload_files():
    uploadedFiles = [] # 2D array of uploaded files (stored in streamlit format) and extensions
    path = st.file_uploader("Upload File(s)", accept_multiple_files=True)
    print("path - " + str(path))
    print("Number of files uploaded by st.file_loader: " + str(len(path)))
    if path:
        for uploaded_file in path:
            print("Inside the for loop")
            file_name, file_extension = os.path.splitext(uploaded_file.name)
            #uploaded_file = st.sidebar.file_uploader("upload", type="csv")
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_file_path = tmp_file.name # filename in temp folder in StreamLit
                print("Temp file name " + tmp_file.name)
                uploadedFiles.append([tmp_file_path, file_extension])
        
        st.session_state.filesuploaded = len(uploadedFiles)
        print("Number of files uploaded: " + str(st.session_state.filesuploaded))
        process_files(uploadedFiles)

def process_files(uploadedFiles):
    data = st.session_state["data"]
    if len(uploadedFiles) > 0:
        for file in uploadedFiles:
            fileName = str(file[0])
            fileExtension = str(file[1])
            print("File Name: " + fileName + " File Extension: " + fileExtension)
            if fileExtension == ".csv":
                print("Loading data for file: " + fileName)
                loader = CSVLoader(file_path=fileName, encoding="utf-8", csv_args={'delimiter': ','})
                #data.append(loader.load())        
                docdata = loader.load()
                print("Data loaded for file: " + fileName)
            elif fileExtension == ".pdf":
                print("Loading data for file: " + fileName)
                loader = PyPDFLoader(file_path=fileName)
                #data.append(loader.load())        
                docdata = loader.load()
                print("Data loaded for file: " + fileName)
            elif fileExtension == ".txt":
                print("Loading data for file: " + fileName)
                loader = TextLoader(fileName, encoding='utf8')
                #data.append(loader.load())          
                docdata = loader.load()
                print("Data loaded for file: " + fileName)
            
        # Since docdata is a list of dictionaries, we need to iterate over it
        for doc in docdata: 
            data.append(doc)
    
        #st.write(data)
        st.session_state["data"] = data
        st.session_state.dataLoaded = True

        # Step 1: Create the LangChain Model (LLM wrapper)
        langchain_model = ChatOpenAI(temperature=0.0,model_name="gpt-3.5-turbo", openai_api_key=API_KEY)

        # Step 2: Create the embeddings
        embeddings = OpenAIEmbeddings(openai_api_key=API_KEY)
        #print("Inside start chat: ")
        #print("Trying to print the data of size: " + str(len(data)))
        #st.write(data)

        # Step 3: Create the vectorstore
        vectorstore = FAISS.from_documents(data, embeddings)

        # Step 4: Create the conversational chain
        chain = ConversationalRetrievalChain.from_llm(llm = langchain_model, retriever=vectorstore.as_retriever())
        st.session_state.chain = chain
        
        st.write("Files Uploaded and Processed Successfully. You can start asking questions now")
   
def extract_data():
    # Implement the Extracting logic here
    st.write("Extracting data...")

def edit_data():
    # Implement the editing logic here
    print("Edit Button clicked!")    

def data_assmltn_form():
    #placeholder = st.empty()
    print("In form")
        
    #with placeholder.form('data_assmltn_form'):
    st.markdown("<h3 style='font-size: 20px; align='center''>Data Assimilation</h3>", unsafe_allow_html=True)
    st.markdown("""    <style>    .stButton button {height: 40px;  } </style>""",    unsafe_allow_html=True)
    col1, col2 = st.columns([6,2.5])

    url = col1.text_input("URL for web crawling")
    with col2:
        html_code = f'<div style="line-height: {1.8};">&nbsp;</div>'
        st.write(html_code, unsafe_allow_html=True)
        extract_button = st.button('Extract data') 

    path = col1.text_input("Data storage Location")
    with col2:
        html_code = f'<div style="line-height: {1.8};">&nbsp;</div>'
        st.write(html_code, unsafe_allow_html=True)
        edit_button = st.button('Edit')   

    if st.session_state.dataLoaded == False:
        print("Call upload_files")
        upload_files()

    if extract_button:
        extract_data()

    if edit_button:
        edit_data()         

if __name__ == '__main__':
     print("In main")
     data_assmltn_form()