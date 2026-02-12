import base64
import os
import random
from pathlib import Path
from typing import List
import streamlit as st
import streamlit.components.v1 as components
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.chat_models import ChatOpenAI
from langchain.chains import ConversationalRetrievalChain
from langchain.document_loaders.csv_loader import CSVLoader
from langchain.document_loaders import PyPDFLoader
from langchain.document_loaders import TextLoader
from langchain.vectorstores import FAISS
from langchain.document_loaders import DirectoryLoader
from langchain.text_splitter import CharacterTextSplitter

def render_svg(svg: Path) -> str:
    """Renders the given svg string."""
    with open(svg) as file:
        b64 = base64.b64encode(file.read().encode("utf-8")).decode("utf-8")
        return f"<img src='data:image/svg+xml;base64,{b64}'/>"


def get_files_in_dir(path: Path) -> List[str]:
    files = []
    for file in os.listdir(path):
        if os.path.isfile(os.path.join(path, file)):
            files.append(file)
    return files


def get_random_img(img_names: list[str]) -> str:
    return random.choice(img_names)

# try this new method for uploading multiple documents at one shot
def load_all_documents():

    datadir = '/Users/rajibdassharma/Python/data/'
    st.write("Please wait. Document uploading in progress...")
    
    pdf_loader = DirectoryLoader(datadir, glob="**/*.pdf")
    txt_loader = DirectoryLoader(datadir, glob="**/*.txt")
    word_loader = DirectoryLoader(datadir, glob="**/*.docx")
    excel_loader = DirectoryLoader(datadir, glob="**/*.xlsx")
    csv_loader = DirectoryLoader(datadir, glob="**/*.csv")
    ppt_loader = DirectoryLoader(datadir, glob="**/*.pptx")

    loaders = [pdf_loader, txt_loader, word_loader, excel_loader, csv_loader, ppt_loader]
    documents = []
    for loader in loaders:
        documents.extend(loader.load())
    print(f"Total number of documents: {len(documents)}")

    # There is problem with the Text Splitter. Debug this in a later version.
    text_splitter = CharacterTextSplitter(separator = "\n\n", chunk_size=1000, chunk_overlap=0) # Split the documents into smaller chunks
    documents = text_splitter.split_documents(documents)

    st.session_state.dataLoaded = True

    #st.write(data)
    st.session_state["data"] = documents
    st.session_state["dataLoaded"] = True

