"""
Second working version of the chatbot.
Date: 22.7.2023
Author: Rajib Das Sharma
Features:
1. Upload file(s)
2. Chat with the bot
3. Prompt button
4. Add the Voice interface - a Talk button in the chat window next to Send (remove the Radio buttons)
5. Add the Help button
6. Add the Search button (AI Agent)
7. Generate Text, Image
8. Integration with User Manager, DataAssimilation programs/screens
9. Give option to the user to select the model


Tech Stack:
1. Streamlit - for User Interface and Web Application
2. LangChain - for memory of the Conversation and Context
3. OpenAI - for the AI Model
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
from langchain.document_loaders import Docx2txtLoader
from langchain.document_loaders import UnstructuredPowerPointLoader
from langchain.document_loaders import UnstructuredExcelLoader
from langchain.document_loaders import UnstructuredWordDocumentLoader
from langchain.vectorstores import FAISS
from langchain.document_loaders import DirectoryLoader
from langchain.text_splitter import CharacterTextSplitter

from streamlit_chat import message
from src.styles.menu_styles import FOOTER_STYLES, HEADER_STYLES
from src.utils.conversation import get_user_input, show_chat_buttons, show_conversation, show_voice_input
from src.utils.footer import show_info
from src.utils.helpers import get_files_in_dir, get_random_img
from src.utils.lang import en
from src.utils.constants import AI_GENERATE_OPTIONS, AI_IMAGE_RES_OPTIONS, AI_MODEL_OPTIONS

# Import the required module for text 
# to speech conversion
from gtts import gTTS
from gtts.tokenizer.pre_processors import abbreviations, end_of_line
from pygame import mixer
import time


from Audio2Text import voice_to_text
from AIAgent import AIAgentSearch
from GenerateContent import generate_image, generate_sm_content
from MainLogin import main_login
from SamplePrompts import show_prompts
from DataAssimilation import data_assmltn_form
from UploadFiles import upload_files

from secret_key import API_KEY, HUGGINGFACE_API_KEY

# --- PATH SETTINGS ---
current_dir: Path = Path(__file__).parent if "__file__" in locals() else Path.cwd()
print("Current Directory Path:", current_dir)
css_file: Path = current_dir / "src/styles/.css"
assets_dir: Path = current_dir / "assets"
icons_dir: Path = assets_dir / "icons"
img_dir: Path = assets_dir / "img"
tg_svg: Path = icons_dir / "tg.svg"

# --- GENERAL SETTINGS ---
PAGE_TITLE: str = "Your AI Assistant - 1.0"
PAGE_ICON: str = "🤖"
LANG_EN: str = "En"
AI_MODEL_NAME = "gpt-3.5-turbo" #hard coded for now. Will be configurable later

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
if "login_success" not in st.session_state:
    st.session_state.login_success = False
if "login_info" not in st.session_state:
    st.session_state.login_info = {}
if "user_info" not in st.session_state:
    st.session_state.user_info = {}
if "voicechat_speak" not in st.session_state:
    st.session_state.voicechat_speak = False
if "voicechat_stop" not in st.session_state:
    st.session_state.voicechat_stop = False
if "voice_text_input" not in st.session_state:
    st.session_state.voice_text_input = ""
if "bulk_upload" not in st.session_state:
    st.session_state.bulk_upload = False

## upload_files and process_files are moved to UploadFiles.py
## moved on 23.7.2023 by RDS

def conversational_chat(query):
        chain = st.session_state.chain
        result = chain({"question": query, "chat_history": st.session_state['history']})
        st.session_state['history'].append((query, result["answer"]))
        
        return result["answer"]

## Added on 16.7.2023
## Added by RDS
def start_text_chat():
    
        data = st.session_state["data"]
        if len(data) > 0:
            print("Starting the chat.....")
  
            #container for the user's text input
            user_input_container = st.container()

            #container for the chat history
            response_container = st.container()

            output = ""

            with user_input_container:
                #with st.form(key='my_form', clear_on_submit=True):
                user_input = st.text_input("Query:", placeholder="Ask me questions about your data here ", key='input')
                c1, c2, c3, c4 = st.columns(4)
                with c1, c2, c3, c4:
                    submit_button = c1.button(label='Ask')
                    save_totext_button = c2.button(label='Save Chat to Text')
                    save_toaudio_button = c3.button(label='Save Chat to Audio')
                    play_audio_button = c4.button(label='Play Audio')
                    #save_button = c2.download_button(
                    #                label=st.session_state.locale.chat_save_btn,
                    #                data="\n".join([str(d) for d in st.session_state["messages"]]),
                    #                file_name="yaia-chat.json",
                    #                mime="application/json",
                    #                )

                if submit_button and user_input:
                    output = conversational_chat(user_input)
                    
                    st.session_state['past'].append(user_input)
                    st.session_state['generated'].append(output)
                    #st.write(output)
                    st.session_state['messages'].append(user_input) # storing the chat history
                    st.session_state['messages'].append(output) # storing the chat history

                if save_totext_button:
                    chat_file = open("yaia-chat.txt", "w")
                    n = chat_file.write("\n".join([str(d) for d in st.session_state["messages"]]))
                    chat_file.close()
                if save_toaudio_button:
                    textStr = "\n".join([str(d) for d in st.session_state["messages"]])
                    language = 'en'
                    tts = gTTS(textStr, lang=language, slow=False, pre_processor_funcs = [abbreviations, end_of_line]) 
                    # Save the audio in a mp3 file
                    tts.save('yaia-chat.mp3')
                if play_audio_button:
                    # Play the audio
                    mixer.init()
                    mixer.music.load("yaia-chat.mp3")
                    mixer.music.play()
                    # Wait for the audio to be played
                    time.sleep(2)

            if st.session_state['generated']:
                with response_container:
                    for i in range(len(st.session_state['generated'])):
                        message(st.session_state["past"][i], is_user=True, key=str(i) + '_user', avatar_style="big-smile")
                        message(st.session_state["generated"][i], key=str(i), avatar_style="thumbs")


def start_search():
    
    response_container = st.container()
    #container for the user's text input
    user_input_container = st.container()

    with user_input_container:
        with st.form(key='my_form', clear_on_submit=True):
            
            user_input = st.text_input("Query:", placeholder="Search the Internet", key='input')
            submit_button = st.form_submit_button(label='Search')
            
        if submit_button and user_input:
            output = AIAgentSearch(user_input)
            response_container.write(output)

## Added on 15.7.2023
## Added by RDS
def generate_content():
    
    st.title('Generate Content')
    c1, c2 = st.columns(2)
    with c1, c2:
            input_kind = c1.radio(
            label=st.session_state.locale.radio_placeholder,
            options=(st.session_state.locale.radio_text1, st.session_state.locale.radio_text2),
            horizontal=True,
        )
    c1, c2, c3 = st.columns(3)
    with c1, c2, c3:
        contentType = c1.selectbox(label="Select the Type of content", key="type", options=AI_GENERATE_OPTIONS)
        imageRes = c2.selectbox(label="For Image, select resolution", key="res", options=AI_IMAGE_RES_OPTIONS)
        imageNum = c3.number_input(label="For Image, select number of images", key="num", min_value=1, max_value=10, value=1)
    
    response_container = st.container()
    #container for the user's text input
    user_input_container = st.container()
    with user_input_container:
        with st.form(key='sm_form', clear_on_submit=True):
            if input_kind == st.session_state.locale.radio_text1:
                user_input = st.text_input('Enter your Topic: ')
                submit_button = st.form_submit_button(label='Generate')
            elif input_kind == st.session_state.locale.radio_text2:
                user_input = st.text_input('Please tell me your Topic: ')
                c1, c2  = st.columns(2)
                with c1, c2:
                    submit_button = c1.form_submit_button(label='Speak')
                    if submit_button:
                        st.session_state.voice_text_input = ""
                        speak_button = False
                        st.session_state.voice_text_input = voice_to_text()
                        user_input = st.session_state.voice_text_input

        if submit_button and user_input:
            if contentType == "Image":
                output = generate_image(user_input, imageNum, imageRes)
                st.image(output)
            else:
                st.write(contentType)
                output = generate_sm_content(user_input, contentType)
                response_container.write(output)

# Created By: RDS
# Created On: 18.7.2023
def start_voice_chat():
        data = st.session_state["data"]
        if len(data) > 0:
            print("Starting the voice chat.....")

            #container for the chat history
            response_container = st.container()
            #container for the user's text input
            user_input_container = st.container()

            with user_input_container:
                with st.form(key='my_form', clear_on_submit=True):
                    
                    user_input = st.text_input("Query:", placeholder= st.session_state.voice_text_input, key='input')
                    
                    #c1, c2  = st.columns(2)
                    speak_button = st.form_submit_button(label='Speak')
                    #send_submit_button = c2.form_submit_button(label='Send')

                if speak_button:
                    st.session_state.voice_text_input = ""
                    speak_button = False
                    st.session_state.voice_text_input = voice_to_text()
                #elif send_submit_button and st.session_state.voice_text_input:
                    output = conversational_chat(st.session_state.voice_text_input)
                    st.write(output)
                    #Convert the text to audio
                    language = 'en'
                    tts = gTTS(output, lang=language, slow=False, pre_processor_funcs = [abbreviations, end_of_line]) 
                    # Save the audio in a mp3 file
                    tts.save('voicechat.mp3')
                    # Play the audio
                    mixer.init()
                    mixer.music.load("voicechat.mp3")
                    mixer.music.play()
                    # Wait for the audio to be played
                    time.sleep(2)
                    
                    #st.session_state['past'].append(st.session_state.voice_text_input)
                    #st.session_state['generated'].append(output)

            #if st.session_state['generated']:
            #    with response_container:
            #        for i in range(len(st.session_state['generated'])):
            #            message(st.session_state["past"][i], is_user=True, key=str(i) + '_user', avatar_style="big-smile")
            #            message(st.session_state["generated"][i], key=str(i), avatar_style="thumbs")


# Working version of the Text Chat as of 16.7.2023. Rewriting this to start_ctext_chat.
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
                    
                    user_input = st.text_input("Query:", placeholder="Ask me questions about your data here ", key='input')
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
        input_kind = c1.radio(
            label=st.session_state.locale.radio_placeholder,
            options=(st.session_state.locale.radio_text1, st.session_state.locale.radio_text2),
            horizontal=True,
        )
       
    if input_kind == st.session_state.locale.radio_text1:
         start_text_chat()
    elif input_kind == st.session_state.locale.radio_text2:
        start_voice_chat()

def launch_program():
    st.session_state.locale = en
    domain = st.session_state.login_info['domain']
    st.markdown(f"<h1 style='text-align: center;'>{PAGE_TITLE}</h1>", unsafe_allow_html=True)
    #if st.session_state.show_upload_heading == True:
    #    st.markdown(f"<h2 style='text-align: center;'>Please upload additional document (s)</h2>", unsafe_allow_html=True)
    selected_option = option_menu(
        menu_title=None,
        options=[
            st.session_state.locale.footer_option0, # "Upload Files" defined in lang.py
            st.session_state.locale.footer_option1, # "Chat" defined in lang.py
            st.session_state.locale.footer_option2, # "Generate Content" defined in lang.py
            st.session_state.locale.footer_option3, # "Search" defined in lang.py
            st.session_state.locale.footer_option4, # "Prompts" defined in lang.py and context sensitive to the Domain
            #st.session_state.locale.footer_option5, # "About" defined in lang.py
        ],
        #icons=["info-circle", "chat-square-text", "piggy-bank"],  # https://icons.getbootstrap.com/
        #menu_icon="cast",
        default_index=0,
        orientation="horizontal",
        styles=HEADER_STYLES
    )

    if selected_option == st.session_state.locale.footer_option0:
        #if st.session_state.dataLoaded == False: Commented to give the user the option to upload files again
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
        generate_content()
    elif selected_option == st.session_state.locale.footer_option3:
        start_search()
    elif selected_option == st.session_state.locale.footer_option4:
        show_prompts(domain)
    elif selected_option == st.session_state.locale.footer_option5:
        show_info()

if __name__ == "__main__":
        numfiles = 0
        if st.session_state.login_success == False:
            st.session_state.login_success = main_login()
        print("Login Status: " + str(st.session_state.login_success))
        if st.session_state.login_success == True:
            role = st.session_state.user_info['role']
            if role == "admin":
                if st.session_state.bulk_upload == True:
                    numfiles = data_assmltn_form()
                    if numfiles > 0:
                        launch_program()
                else:
                    launch_program()
            else:
                launch_program()

