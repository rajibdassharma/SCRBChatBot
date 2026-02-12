# Created By: Rajib Das Sharma
# Created on: 13th July 2023

# This program will take an URL and download all the contents of the page

import requests
from bs4 import BeautifulSoup
import pandas as pd

from src.utils.constants import DATA_DIR

class Content:
    def __init__(self, url, title, body, paragraphs, tables):
        self.url = url
        self.title = title
        self.body = body
        self.paragraphs = paragraphs
        self.tables = tables

def getPage(url):
    req = requests.get(url)
    return BeautifulSoup(req.text, 'html.parser')

def scrapeURL(url):
    bs = getPage(url)
    title = bs.find('h1').text
    body = bs.find()
    return Content(url, title, body)

def scrape_tables(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # Find all table elements
    tables = soup.find_all('table')

    # For each table, convert it into a pandas DataFrame and print it
    for i, table in enumerate(tables):
        df = pd.read_html(str(table))[0]
        print(f"Table {i+1}:")
        print(df)
        print("\n---\n")
    

def scrape_website(url):
    
    bs = getPage(url)
    title = bs.find('h1').text
    body = bs.find()
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    # Find all paragraphs
    paragraphs = soup.find_all('p')
    # Find all table elements
    tables = soup.find_all('table')
    return Content(url, title, body, paragraphs, tables)


'''
url = 'https://www.brookings.edu/blog/future-development/2018/01/26/''delivering-inclusive-urban-access-3-uncomfortable-truths/'
content = scrapeBrookings(url)
print('Title: {}'.format(content.title))
print('URL: {}\n'.format(content.url))
print(content.body)

url = 'https://www.nytimes.com/2018/01/25/opinion/sunday/''silicon-valley-immortality.html'
content = scrapeNYTimes(url)
print('Title: {}'.format(content.title))
print('URL: {}\n'.format(content.url))
print(content.body)

'''

def extract_text_from(url):
    html = requests.get(url).text
    soup = BeautifulSoup(html, features="html.parser")
    text = soup.get_text()

    lines = (line.strip() for line in text.splitlines())
    return '\n'.join(line for line in lines if line)


def scrape_url(url, folderName):

    print("In scrape_url....." + url + " " + folderName)
    content = scrape_website(url)
    title_data = 'Title: {}'.format(content.title)
    url_data = 'URL: {}\n'.format(content.url)


    # general text is stored in the .txt file
    fileName =  folderName + "/" + 'Text.txt'
    with open(fileName, 'w') as f:
            lines = extract_text_from(url)
            f.write(lines)
            f.close()

'''
    # tables are stored in .csv files
    for i, table in enumerate(content.tables):
        df = pd.read_html(str(table))[0]
        fName = folderName + "/" +  f"Table {i+1}" + '.csv'
        f = open(fName, 'w')
        df.to_csv(f)
        f.close()
        i += 1
'''
'''
from langchain.document_loaders import DirectoryLoader
from langchain.text_splitter import CharacterTextSplitter

data = []
folderName = '/Users/rajibdassharma/YAIA/data/Webcrawl'
textLoader = DirectoryLoader(folderName, glob="**/*.txt")
textDocuments = textLoader.load()
text_splitter = CharacterTextSplitter(chunk_size=1500, separator="\n")

for doc in textDocuments:
    docs = []
    splits = text_splitter.split_text(doc.page_content)
    print(splits)
    docs.extend(splits)
    data.append(docs)
'''
