from typing import Literal
from ollama import Client
from langgraph.graph import END
from database import GraphDB
from state import agent_state
import config 
from neo4j import GraphDatabase

import logging 
import re
from schema_extract import get_schema,get_structured_schema

_CYPHER_START_RE = re.compile(r"\b(MATCH|MERGE|CREATE|DELETE|DETACH|SET|REMOVE|WITH|CALL|UNWIND)\b", re.IGNORECASE)





def extract_schema(state: agent_state):
    logging.info("Extracting graph schema preprocessing...")
    db = GraphDB(state["login_url"], state["login_user"], state["login_password"])
    output = get_structured_schema(db)
    database_description = get_schema(output)
    db.close()
    logging.info("Schema generated successfully.")
    return {"database_description": database_description}

def describe_query(state:agent_state,query):
    #add a log if the connection did not go through 
    try:
        client = Client(
            host=config.OLLAMA_HOST,
            headers=config.OLLAMA_AUTH_HEADER
        )

    except Exception as e:
        logging.error("Failed Connection to Ollama")


    database_description=state["database_description"]
    print("The Description of the Input:")
    fquestion = f"""
    {database_description}
    Describe this query:{query} in detail,make a short paragraph.
    Return only the paragraph.
    """
    messages = [{"role": "user", "content": fquestion}]

    for part in client.chat(config.OLLAMA_MODEL, messages=messages, stream=True):
        print(part['message']['content'], end='', flush=True)
    
    return query 

def query_is_correct(string):
    cleaned = string.replace("```cypher", "").replace("```", "").strip()
    match = _CYPHER_START_RE.search(cleaned)
    if match:
        cleaned = cleaned[match.start() :]
    semicolon = cleaned.find(";")
    if semicolon != -1:
        cleaned = cleaned[: semicolon + 1]
    cleaned = " ".join(cleaned.split())
    print(cleaned)
    return cleaned

def generate_repairs(state: agent_state):
    query = state["query"]
    database_description=state["database_description"]
    formatted_inconsistency = describe_query(state,query)
    repairs = ""

    try:
        client = Client(
            host=config.OLLAMA_HOST,
            headers=config.OLLAMA_AUTH_HEADER
        )
    except Exception as e:
        logging.error("Failed Connection to Ollama")
    
    NEO4J_URL = state["login_url"]
    NEO4J_PASSWORD = state["login_password"]
    NEO4J_USER = state["login_user"]

    

    
    fquestion = f"""
    {database_description}
    The database has inconsistencies that we want to remove.
    One such inconsistency is{formatted_inconsistency}.
    You can delete an edge, a node, replace a edge or replace a node. But only one change.
    Please generate all possible queries that could fix this.
    IMP:When generating the query also remember to use the description to retrieve the pattern then remove the inconsisteny.
    Return only the cypher queries. For now only one.
    Make sure it is in proper format with a semi-colon denoting the end.
    (Generate the cypher queries only.)
    """

    messages = [{"role": "user", "content": fquestion}]

    print("The Generated Query for repair:\n")
    for part in client.chat(config.OLLAMA_MODEL, messages=messages, stream=True):
        repairs = repairs + part['message']['content']

    print(repairs)
    repairs = query_is_correct(repairs)
    return {"repairs": repairs}

def retrieve(state: agent_state):
    curr_query = state["query"]
    print(curr_query)
    
    
    NEO4J_URL = state["login_url"]
    NEO4J_PASSWORD = state["login_password"]
    NEO4J_USER = state["login_user"]

    db = GraphDB(NEO4J_URL, NEO4J_USER, NEO4J_PASSWORD)
    results = db.run_query(curr_query)
    db.close()

    return {"results": results}

def apply(state: agent_state):
    curr_query = state["repairs"]
    NEO4J_URL = state["login_url"]
    NEO4J_PASSWORD = state["login_password"]
    NEO4J_USER = state["login_user"]

    db = GraphDB(NEO4J_URL, NEO4J_USER, NEO4J_PASSWORD)
    results = db.run_query(curr_query)
    db.close()

def manager(state: agent_state):
    logging.basicConfig(level=logging.INFO,filename="log.log",filemode="w",
                    format="%(asctime)s -%(levelname)s -%(message)s")
    
    list_of_inconsistencies=state["list_of_inconsistencies"]
    cycle_count = state.get("cycle_count", 0)
    MAX_CYCLES = 50
    
    message=None
    if len(list_of_inconsistencies) == 0 or cycle_count >= MAX_CYCLES:
    
        message="EXIT"
        if cycle_count >= MAX_CYCLES:
            logging.warning(f"Manager has initiated an exit due to cycle limit ({MAX_CYCLES}).")
        else:
            logging.info(f"Manager has intiated an exit .")

    
    else:
        message=list_of_inconsistencies.pop()
        logging.info(f"Manager has successfully gotten query:{message}")

    

        
    
    if message == "EXIT":
        return {"status": "EXIT", "cycle_count": cycle_count + 1}
    else:
        return {"status": "Processing", "query": message, "cycle_count": cycle_count + 1}


def check_manager_status(state: agent_state) -> Literal[END, "retrieve"]:
    logging.info("Checking whether the user wants to exit or not.")
    status = state["status"]
    if status == "EXIT":
        print("You have exited the process.")
        logging.info("Successfully Exited. :)")
        return END
    else:
        return "retrieve"
    
    

def evaluate_retrieval_results(state: agent_state) -> Literal["manager", "generate_repairs"]:
    logging.info("Checking whether the such patterns exist in the graph.")

    if len(state["results"]) == 0:
        print("No such patterns in the knowledge graph.")
        return "manager"
    else:
        return "generate_repairs"

def verify_repairs(state: agent_state) -> Literal["manager", "generate_repairs"]:
    logging.info("Repairing the graph...")

    # Uses global config for connection as per original logic style
    db = GraphDB(config.NEO4J_URL, config.NEO4J_USERNAME, config.NEO4J_PASSWORD)
    logging.info("Applying the changes.")
    
    results = db.run_query(state["query"])
    db.close()
    if len(results) == 0:
        print("Repairs were done.")
        return "manager"
    else:
        return "generate_repairs"