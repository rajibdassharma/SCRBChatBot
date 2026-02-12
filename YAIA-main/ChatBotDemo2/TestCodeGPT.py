import streamlit as st
import openai
import json
from  secret_key import OPENAI_API_KEY

# Set OpenAI API key
openai.api_key = OPENAI_API_KEY

st.title('ChatGPT')

# Define initial user message
user_message = st.text_input('User :')
messages = []

# Main interaction loop
while True:
    if user_message:
        # Add user message to list of messages
        messages.append({'role': 'user', 'content': user_message})

        # Query ChatGPT for response
        response = openai.Completion.create(
            engine='gpt-3.5-turbo',
            prompt=json.dumps(messages),
            max_tokens=50,
            n=1,
            stop=None,
            temperature=0.7,
        )
        
        # Add model response to list of messages
        messages.append({'role': 'ChatGPT', 'content': response.choices[0].text.strip()})
        
        # Clear user input for next message
        user_message = ''

    # Display messages
    for message in messages:
        if message['role'] == 'user':
            st.text_input('User:', value=message['content'], disabled=True)
        else:
            st.text_area('ChatGPT:', value=message['content'], disabled=True)

    # User input for next message
    #user_message = st.text_input('User :')

