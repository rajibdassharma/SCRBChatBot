import openai
import os
from secret_key import API_KEY

openai.api_key  = API_KEY

def get_completion(prompt, model="gpt-3.5-turbo"):
    messages = [{"role": "user", "content": prompt}]
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=0, # this is the degree of randomness of the model's output
    )
    return response.choices[0].message["content"]

prompt = "What is the meaning of life?"

response = get_completion(prompt)

print(response)
