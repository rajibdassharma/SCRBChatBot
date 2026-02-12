# Created By: Rajib Das Sharma
# Created on: 13th July 2023

# This program will take an URL and download all the contents of the page

import requests
from bs4 import BeautifulSoup
import pandas as pd

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

url = 'https://en.wikipedia.org/wiki/Nvidia'
content = scrape_website(url)
title = 'Title: {}'.format(content.title)
url = 'URL: {}\n'.format(content.url)
with open('test.txt', 'w') as f:
        f.write(title)
        f.write('\n')
        f.write(url)
        f.write('\n')
        for p in content.paragraphs:
            f.write(p.get_text())
        f.close()

for i, table in enumerate(content.tables):
    df = pd.read_html(str(table))[0]
    fName = f"Table {i+1}:" + '.csv'
    f = open(fName, 'a')
    df.to_csv(f)
    f.close()
    i += 1
