# Importing necessary packages, files and services
import os
import openai
import io

import json
from base64 import b64decode
from pathlib import Path

import streamlit as st 
from langchain.llms import OpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain, SequentialChain 
from langchain.memory import ConversationBufferMemory
#from langchain.utilities import WikipediaAPIWrapper

from huggingface_hub import InferenceClient

from secret_key import API_KEY


# App UI framework
#st.title('🦜🔗 Tweet Generator')
#prompt = st.text_input('Tweet topic: ') 

def generate_image(inputStr, numImages, resolution):

    image_model = st.session_state.login_info['image_model']
    if image_model == "DALL-E 2":
        image = generate_dalle2_image(inputStr, numImages, resolution)
    elif image_model == "Hugging Face":
        image = generate_huggingface_image(inputStr)
    return image

def generate_tweet(prompt):
# Prompt templates
    title_template = PromptTemplate(
                    input_variables = ['topic'], 
                    template='write me a Tweet about {topic}'
                    )


    #tweet_template = PromptTemplate(
    #            input_variables = ['title'], 
    #            template='write me a tweet on this title TITLE: {title}'
    #            )


    # Wikipedia data
    #wiki = WikipediaAPIWrapper()

    # Memory 
    title_memory = ConversationBufferMemory(input_key='topic', memory_key='chat_history')
    #tweet_memory = ConversationBufferMemory(input_key='title', memory_key='chat_history')


    # Llms
    llm = OpenAI(model_name="text-davinci-003", temperature=0.9, openai_api_key=API_KEY) 
    title_chain = LLMChain(llm=llm, prompt=title_template, verbose=True, output_key='title', memory=title_memory)
    #tweet_chain = LLMChain(llm=llm, prompt=tweet_template, verbose=True, output_key='script', memory=tweet_memory)

    # Chaining the components and displaying outputs
    if prompt: 
        title = title_chain.run(prompt)
        #wiki_research = wiki.run(prompt) 
        #tweet = tweet_chain.run(title=title)

        """"
        st.write(title) 
        st.write(tweet) 

        with st.expander('Title History'): 
            st.info(title_memory.buffer)

        with st.expander('Tweet History'): 
            st.info(tweet_memory.buffer)

        with st.expander('Wikipedia Research'): 
            st.info(wiki_research)
        """
        #st.write(title) 
        return title
    
def generate_linkedin_post(prompt):
# Prompt templates
    title_template = PromptTemplate(
                    input_variables = ['topic'], 
                    template='write me a LinkedIn Post about {topic} in 100 words or less'
                    )
    # Memory 
    title_memory = ConversationBufferMemory(input_key='topic', memory_key='chat_history')
    # Llms
    llm = OpenAI(model_name="text-davinci-003", temperature=0.9, openai_api_key=OPENAI_API_KEY) 
    title_chain = LLMChain(llm=llm, prompt=title_template, verbose=True, output_key='title', memory=title_memory)
    # Chaining the components and displaying outputs
    if prompt: 
        title = title_chain.run(prompt)
        return title
    
def generate_email(prompt):
# Prompt templates
    title_template = PromptTemplate(
                    input_variables = ['topic'], 
                    template='Please generate an email on {topic} in polite tone in 100 words or less'
                    )
    # Memory 
    title_memory = ConversationBufferMemory(input_key='topic', memory_key='chat_history')
    # Llms
    llm = OpenAI(model_name="text-davinci-003", temperature=0.9, openai_api_key=OPENAI_API_KEY) 
    title_chain = LLMChain(llm=llm, prompt=title_template, verbose=True, output_key='title', memory=title_memory)
    # Chaining the components and displaying outputs
    if prompt: 
        title = title_chain.run(prompt)
        return title
    

def generate_facebook_post(prompt):
    # Prompt templates
    title_template = PromptTemplate(
                    input_variables = ['topic'], 
                    template='write me a Facebook Post about {topic} in 50 words or less'
                    )
    # Memory 
    title_memory = ConversationBufferMemory(input_key='topic', memory_key='chat_history')
    # Llms
    llm = OpenAI(model_name="text-davinci-003", temperature=0.9, openai_api_key=OPENAI_API_KEY) 
    title_chain = LLMChain(llm=llm, prompt=title_template, verbose=True, output_key='title', memory=title_memory)
    # Chaining the components and displaying outputs
    if prompt: 
        title = title_chain.run(prompt)
        return title
    
def generate_sm_content(inputStr, contentType):

    output = ""
    if contentType == "Tweet":
        output = generate_tweet(inputStr)
    elif contentType == "LinkedIn Post":
        output = generate_linkedin_post(inputStr)
    elif contentType == "Facebook Post":
        output = generate_facebook_post(inputStr)
    elif contentType == "eMail":
        output = generate_email(inputStr)
    return output

def generate_dalle2_image(inputStr, numImages, resolution):

    openai.api_key = OPENAI_API_KEY
    response = openai.Image.create(
                                prompt=inputStr, # The prompt(s) to generate from.
                                n=numImages, # Number of images to create.
                                size=resolution, # Image size in pixels.
                                )
    #print(response["data"][0]["url"])
    return response["data"][0]["url"]

    
def generate_huggingface_image(inputStr):
    model="prompthero/openjourney-v4"
    client = InferenceClient(model)
    image = client.text_to_image(inputStr)
    #image.save("astronaut.png")
    return image

def generate_save_dalle2_image(inputStr, numImages, resolution):

    PROMPT = inputStr
    openai.api_key = OPENAI_API_KEY
    response = openai.Image.create(
                                prompt=inputStr, # The prompt(s) to generate from.
                                n=numImages, # Number of images to create.
                                size=resolution, # Image size in pixels.
                                response_format="b64_json",
                            )
    path = "/Users/rajibdassharma/Python/data/DALLE2"
    DATA_DIR = path + "/data/"
    IMAGE_DIR = path + "/images/"
    
    data_file_name = DATA_DIR + "imagedata.json"

    with open(data_file_name, mode="w", encoding="utf-8") as file:
        json.dump(response, file)

    with open(data_file_name, mode="r", encoding="utf-8") as file:
        response = json.load(file)

    for index, image_dict in enumerate(response["data"]):
        image_data = b64decode(image_dict["b64_json"])
        image_file = IMAGE_DIR + inputStr + "image.png"
        with open(image_file, mode="wb") as png:
            png.write(image_data)
    
    return response["data"][0]["url"]

