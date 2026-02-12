"""
First working version of the chatbot.
Date: 30-6.2023
Author: Rajib Das Sharma
Features:
1. Upload file(s)
2. Chat with the bot

Tech Stack:
1. Streamlit
2. LangChain
3. OpenAI
4. FAISS (Pinecone or similar vector database will be used in a later version)
5. Python
"""

import tempfile
import os
from pathlib import Path
from random import randrange

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
from src.utils.footer import show_donates, show_info
from src.utils.helpers import get_files_in_dir, get_random_img
from src.utils.lang import en

from secret_key import API_KEY

# --- PATH SETTINGS ---
current_dir: Path = Path(__file__).parent if "__file__" in locals() else Path.cwd()
print("Current Directory Path:", current_dir)
css_file: Path = current_dir / "src/styles/.css"
assets_dir: Path = current_dir / "assets"
icons_dir: Path = assets_dir / "icons"
img_dir: Path = assets_dir / "img"
tg_svg: Path = icons_dir / "tg.svg"

# --- GENERAL SETTINGS ---
PAGE_TITLE: str = "Ask Your Document - Demo Version 2"
PAGE_ICON: str = "🤖"
LANG_EN: str = "En"
AI_MODEL_OPTIONS: list[str] = [
    "gpt-3.5-turbo",
#    "gpt-4",
#    "gpt-4-32k",
]

st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON)

# --- LOAD CSS ---
with open(css_file) as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

#Commenting for now. Will use later to add support for other languages
#selected_lang = option_menu(
#    menu_title=None,
#    options=[LANG_EN, LANG_RU, ],
#    icons=["globe2", "translate"],
#    menu_icon="cast",
#    default_index=0,
#    orientation="horizontal",
#    styles=HEADER_STYLES
#)

# Storing The Context
if "locale" not in st.session_state:
    st.session_state.locale = en
if "generated" not in st.session_state:
    st.session_state.generated = []
if "past" not in st.session_state:
    st.session_state.past = []
if "messages" not in st.session_state:
    st.session_state.messages = []
if "user_text" not in st.session_state:
    st.session_state.user_text = ""
if "input_kind" not in st.session_state:
    st.session_state.input_kind = st.session_state.locale.input_kind_1
if "seed" not in st.session_state:
    st.session_state.seed = randrange(10**3)  # noqa: S311
if "costs" not in st.session_state:
    st.session_state.costs = []
if "total_tokens" not in st.session_state:
    st.session_state.total_tokens = []
if "model" not in st.session_state:
    st.session_state.langchain_model = None
if "filesuploaded" not in st.session_state:
    st.session_state.filesuploaded = 0
if "data" not in st.session_state:
    st.session_state["data"] = []
    data = []
if "dataLoaded" not in st.session_state:
    st.session_state.dataLoaded = False
if 'history' not in st.session_state:
    st.session_state['history'] = []
if 'generated' not in st.session_state:
    st.session_state['generated'] = ["Hello ! Ask me anything about the Files you uploaded "  + " 🤗"]
if 'past' not in st.session_state:
    st.session_state['past'] = ["Hey ! 👋"]
if 'chain' not in st.session_state:
    st.session_state['chain'] = None

# try this new method for uploading multiple documents at one shot

def upload_files():

    uploadedFiles = [] # 2D array of uploaded files (stored in streamlit format) and extensions
    path = st.file_uploader("Upload File(s)", accept_multiple_files=True)
    for uploaded_file in path:
        file_name, file_extension = os.path.splitext(uploaded_file.name)
        #uploaded_file = st.sidebar.file_uploader("upload", type="csv")
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_file_path = tmp_file.name # filename in temp folder in StreamLit
            print("Temp file name " + tmp_file.name)
            uploadedFiles.append([tmp_file_path, file_extension])
    
    st.session_state.filesuploaded = len(uploadedFiles)
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

def conversational_chat(query):
        chain = st.session_state.chain
        result = chain({"question": query, "chat_history": st.session_state['history']})
        st.session_state['history'].append((query, result["answer"]))
        
        return result["answer"]

def start_chat():
    
        data = st.session_state["data"]
        if len(data) > 0:
            print("Starting the chat.....")
  
            #container for the chat history
            response_container = st.container()
            #container for the user's text input
            user_input_container = st.container()

            with user_input_container:
                with st.form(key='my_form', clear_on_submit=True):
                    
                    user_input = st.text_input("Query:", placeholder="Ask me questions about you data here ", key='input')
                    submit_button = st.form_submit_button(label='Ask')
                    
                if submit_button and user_input:
                    output = conversational_chat(user_input)
                    
                    st.session_state['past'].append(user_input)
                    st.session_state['generated'].append(output)

            if st.session_state['generated']:
                with response_container:
                    for i in range(len(st.session_state['generated'])):
                        message(st.session_state["past"][i], is_user=True, key=str(i) + '_user', avatar_style="big-smile")
                        message(st.session_state["generated"][i], key=str(i), avatar_style="thumbs")


def main():
    c1, c2 = st.columns(2)
    with c1, c2:
        c1.selectbox(label=st.session_state.locale.select_placeholder1, key="model", options=AI_MODEL_OPTIONS)
        st.session_state.input_kind = c2.radio(
            label=st.session_state.locale.input_kind,
            options=(st.session_state.locale.input_kind_1, st.session_state.locale.input_kind_2),
            horizontal=True,
        )
        c2.selectbox(label=st.session_state.locale.select_placeholder2, key="role",
                            options=st.session_state.locale.ai_role_options)
        
    #if st.session_state.user_text:
    #   show_conversation()
    #    st.session_state.user_text = ""
    #get_user_input()
    #show_chat_buttons()
    start_chat()

def launch_program():
    st.session_state.locale = en
    st.markdown(f"<h1 style='text-align: center;'>{st.session_state.locale.title}</h1>", unsafe_allow_html=True)
    selected_option = option_menu(
        menu_title=None,
        options=[
            st.session_state.locale.footer_option0, # "Upload Files" defined in lang.py
            st.session_state.locale.footer_option1, # "Chat" defined in lang.py
            st.session_state.locale.footer_option2, # "Info" defined in lang.py
            st.session_state.locale.footer_option3, # "Help" defined in lang.py
        ],
        icons=["info-circle", "chat-square-text", "piggy-bank"],  # https://icons.getbootstrap.com/
        menu_icon="cast",
        default_index=0,
        orientation="horizontal",
        styles=FOOTER_STYLES
    )

    if selected_option == st.session_state.locale.footer_option0:
        if st.session_state.dataLoaded == False:
            upload_files()
    elif selected_option == st.session_state.locale.footer_option1:
        if st.session_state.filesuploaded > 0:
            if st.session_state.dataLoaded == True:
                main()
            elif st.session_state.dataLoaded == False:
                st.write("Please wait...Files are being processed")
        else:
            st.write("Please upload the files first")
    elif selected_option == st.session_state.locale.footer_option2:
        st.image(f"{img_dir}/{get_random_img(get_files_in_dir(img_dir))}")
        show_info(tg_svg)
    elif selected_option == st.session_state.locale.footer_option3:
        st.write("Help page under construction")


if __name__ == "__main__":
    launch_program()
