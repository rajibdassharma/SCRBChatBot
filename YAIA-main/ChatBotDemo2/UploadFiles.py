import tempfile
import os
from pathlib import Path
from random import randrange

from langchain.document_loaders.csv_loader import CSVLoader
from langchain.document_loaders import PyPDFLoader
from langchain.document_loaders import TextLoader
from langchain.document_loaders import Docx2txtLoader
from langchain.document_loaders import UnstructuredPowerPointLoader
from langchain.document_loaders import UnstructuredExcelLoader
from langchain.document_loaders import UnstructuredWordDocumentLoader
from langchain.vectorstores import FAISS
from langchain.document_loaders import DirectoryLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain.text_splitter import RecursiveCharacterTextSplitter

from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.chat_models import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain

import streamlit as st

from secret_key import API_KEY, HUGGINGFACE_API_KEY


def upload_process_all_files(folder_paths):

    docList = []
    numfiles = 0
    
    for folderName in folder_paths:
        print("Folder Name: " + folderName)
        textLoader = DirectoryLoader(folderName, glob="**/*.txt")
        textDocuments = textLoader.load()
        for doc in textDocuments:
            docList.append(doc)
            
        pdfLoader = DirectoryLoader(folderName, glob="**/*.pdf")
        pdfDocuments = pdfLoader.load()
        for doc in pdfDocuments: 
            docList.append(doc)
        
        csvLoader = DirectoryLoader(folderName, glob="**/*.csv")
        csvDocuments = csvLoader.load()
        for doc in csvDocuments: 
            docList.append(doc)

    numfiles = len(docList)
    st.session_state.filesuploaded = numfiles
    print("No of files uploaded: " + str(numfiles))

    # Split the data into chunks to overcome the token limit    
    split_data = []
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500,)
    for doc in docList:
        splits = text_splitter.split_text(doc.page_content)
        #print(splits)
        split_data.extend(splits)

    st.session_state["data"] = docList
    st.session_state["split_data"] = split_data
    st.session_state.dataLoaded = True

    create_langchain_chain()

    print("Files Uploaded and Processed Successfully. You can start asking questions now")
    return numfiles

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
    docList = st.session_state["data"]
    if len(uploadedFiles) > 0:
        for file in uploadedFiles:
            fileName = str(file[0])
            fileExtension = str(file[1])
            if fileExtension == ".csv":
                loader = CSVLoader(file_path=fileName, encoding="utf-8", csv_args={'delimiter': ','})       
            elif fileExtension == ".pdf":
                loader = PyPDFLoader(file_path=fileName)     
            elif fileExtension == ".docx":
                loader = UnstructuredWordDocumentLoader(fileName)
            elif fileExtension == ".pptx" or fileExtension == ".ppt":
                loader = UnstructuredPowerPointLoader(fileName)
            elif fileExtension == ".xlsx" or fileExtension == ".xls":
                loader = UnstructuredExcelLoader(fileName)
            elif fileExtension == ".txt":
                loader = TextLoader(fileName, encoding='utf8')    
            
            docdata = loader.load()
            # Since docdata is a list of dictionaries, we need to iterate over it
            for doc in docdata: 
                docList.append(doc)
        
        numfiles = len(docList)
        st.session_state.filesuploaded = numfiles
        print("No of files uploaded: " + str(numfiles))

        # Split the data into chunks to overcome the token limit    
        split_data = []
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500,)
        for doc in docList:
            splits = text_splitter.split_text(doc.page_content)
            #print(splits)
            split_data.extend(splits)

        st.session_state["data"] = docList
        st.session_state["split_data"] = split_data
        st.session_state.dataLoaded = True

        create_langchain_chain()
        
        st.write("Files Uploaded and Processed Successfully. You can start asking questions now")

def create_langchain_chain():

        AI_MODEL_NAME = "gpt-3.5-turbo" #hard coded for now. Will be configurable later

        # Step 1: Create the LangChain Model (LLM wrapper)
        langchain_model = ChatOpenAI(temperature=0.0,model_name=AI_MODEL_NAME, openai_api_key=API_KEY)

        # Step 2: Create the embeddings
        embeddings = OpenAIEmbeddings(openai_api_key=API_KEY)
        #print("Inside start chat: ")
        #print("Trying to print the data of size: " + str(len(data)))
        #st.write(data)

        # Step 3: Create the vectorstore
        #Commented the old way - this is there until StartChat3
        #data = st.session_state["data"]
        #vectorstore = FAISS.from_documents(data, embeddings)

        split_data = st.session_state["split_data"]
        vectorstore = FAISS.from_texts(split_data, embeddings)

        # Step 4: Create the conversational chain
        chain = ConversationalRetrievalChain.from_llm(llm = langchain_model, retriever=vectorstore.as_retriever())
        st.session_state.chain = chain
