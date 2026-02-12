import requests

from langchain import OpenAI
from langchain.agents import initialize_agent, load_tools, Tool
from langchain.tools import DuckDuckGoSearchRun, GoogleSearchRun

from secret_key import API_KEY

OPENAI_API_KEY = API_KEY

llm = OpenAI(openai_api_key=OPENAI_API_KEY, temperature=0.8, model_name="text-davinci-003")

# Web Search Tool
def AIAgentSearch(searchStr: str) -> str:
    """Searches the web for the given query."""
    search = DuckDuckGoSearchRun()

    # Web Search Tool
    search_tool = Tool(
        name = "Web Search",
        func=search.run,
        description="A useful tool for searching the Internet to find information on world events, issues, etc. Worth using for general topics. Use precise questions."
    )

    agent = initialize_agent(
        agent="zero-shot-react-description",
        tools=[search_tool],
        llm=llm,
        verbose=True, # I will use verbose=True to check process of choosing tool by Agent
        max_iterations=4
    )

    r_1 = agent(searchStr)
    return r_1["output"]
