from typing import Literal
from ollama import Client
from langgraph.graph import END
from database import GraphDB
from state import agent_state
import config
from neo4j import GraphDatabase
import logging
import re
from schema_extract import get_schema, get_structured_schema
from neo4j.exceptions import ClientError, CypherSyntaxError
from prompts import DESCRIBE_QUERY_PROMPT, GENERATE_REPAIRS_PROMPT
log = logging.getLogger("nodes")

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
    log.debug("Describing query for context: %s", query[:120])
    fquestion = DESCRIBE_QUERY_PROMPT.format(
        database_description=database_description,
        query=query
    )
    messages = [{"role": "user", "content": fquestion}]

    description_parts = []
    tokens = 0
    _llm_opts = {"seed": config.OLLAMA_SEED, "temperature": config.OLLAMA_TEMPERATURE}
    for part in client.chat(config.OLLAMA_MODEL, messages=messages, stream=True,
                            options=_llm_opts):
        description_parts.append(part.get('message', {}).get('content', ''))
        if 'eval_count' in part:
            tokens += part['eval_count']
        if 'prompt_eval_count' in part:
            tokens += part['prompt_eval_count']
    log.debug("Query description: %s", "".join(description_parts))
    
    return "".join(description_parts), tokens

def query_is_correct(string):
    cleaned = string.replace("```cypher", "").replace("```", "").strip()
    match = _CYPHER_START_RE.search(cleaned)
    if match:
        cleaned = cleaned[match.start() :]
    semicolon = cleaned.find(";")
    if semicolon != -1:
        cleaned = cleaned[: semicolon + 1]
    cleaned = " ".join(cleaned.split())
    log.debug("Cleaned repair query: %s", cleaned)
    return cleaned

def generate_repairs(state: agent_state):
    query = state["query"]
    database_description = state["database_description"]
    total_tokens = state.get("total_tokens", 0)
    log.info("Generating repair for inconsistency: %s", query[:120])
    formatted_inconsistency, extra_tokens = describe_query(state, query)
    total_tokens += extra_tokens
    repairs = ""

    try:
        client = Client(
            host=config.OLLAMA_HOST,
            headers=config.OLLAMA_AUTH_HEADER
        )
    except Exception as e:
        log.error("Failed connection to Ollama: %s", e, exc_info=True)

    fquestion = GENERATE_REPAIRS_PROMPT.format(
        database_description=database_description,
        formatted_inconsistency=formatted_inconsistency
    )

    messages = [{"role": "user", "content": fquestion}]

    log.info("Querying model '%s' for repair query...", config.OLLAMA_MODEL)
    _llm_opts = {"seed": config.OLLAMA_SEED, "temperature": config.OLLAMA_TEMPERATURE}
    for part in client.chat(config.OLLAMA_MODEL, messages=messages, stream=True,
                            options=_llm_opts):
        repairs = repairs + part.get('message', {}).get('content', '')
        if 'eval_count' in part:
            total_tokens += part['eval_count']
        if 'prompt_eval_count' in part:
            total_tokens += part['prompt_eval_count']

    log.info("Raw repair response: %s", repairs)
    cleaned = query_is_correct(repairs)
    if is_the_repair_query_correct(cleaned, state):
        repairs = cleaned
    else:
        log.warning("Generated repair failed syntax check — will retry.")
        cycle_count = state.get("cycle_count", 0) + 1
        return {"repairs": repairs, "cycle_count": cycle_count, "total_tokens": total_tokens}

    log.info("Final repair query: %s", repairs)
    cycle_count = state.get("cycle_count", 0) + 1
    return {"repairs": repairs, "cycle_count": cycle_count, "total_tokens": total_tokens}

def retrieve(state: agent_state):
    curr_query = state["query"]
    log.info("Retrieving inconsistency pattern: %s", curr_query)

    NEO4J_URL = state["login_url"]
    NEO4J_PASSWORD = state["login_password"]
    NEO4J_USER = state["login_user"]

    db = GraphDB(NEO4J_URL, NEO4J_USER, NEO4J_PASSWORD)
    results = db.run_query(curr_query)
    db.close()

    # Update the repair status for the current query
    repair_status_array = list(state.get("repair_status_array", []))
    query_index = state.get("current_index", 1) - 1  # current_index was already incremented by manager

    if query_index < len(repair_status_array):
        if len(results) == 0:
            repair_status_array[query_index] = True
            log.info("Retrieve returned 0 result(s). Marking query %d as repaired.", query_index)
        else:
            repair_status_array[query_index] = False
            log.info("Retrieve returned %d result(s). Query %d still needs repair.", len(results), query_index)

    return {"results": results, "repair_status_array": repair_status_array}

def apply(state: agent_state):
    curr_query = state["repairs"]
    NEO4J_URL = state["login_url"]
    NEO4J_PASSWORD = state["login_password"]
    NEO4J_USER = state["login_user"]

    db = GraphDB(NEO4J_URL, NEO4J_USER, NEO4J_PASSWORD)
    try:
        log.info("Applying repair query: %s", curr_query[:120])
        db.run_query(curr_query)
        log.info("Repair query applied successfully.")
    except CypherSyntaxError as e:
        log.error("Cypher syntax error while applying repair — query will be skipped. Error: %s", e)
    except ClientError as e:
        log.error("Neo4j client error while applying repair — query will be skipped. Error: %s", e)
    except Exception as e:
        log.error("Unexpected error while applying repair — query will be skipped. Error: %s", e, exc_info=True)
    finally:
        db.close()

def manager(state: agent_state):
    list_of_inconsistencies = state["list_of_inconsistencies"]
    current_index = state.get("current_index", 0)
    iteration_count = state.get("iteration_count", 0)
    repair_status_array = list(state.get("repair_status_array", [False] * len(list_of_inconsistencies)))
    prev_repair_status_array = list(state.get("prev_repair_status_array", []))

    if len(list_of_inconsistencies) == 0:
        log.info("Manager exiting: no inconsistencies to process.")
        return {"status": "EXIT"}

    # Check if we've completed a full pass through all inconsistencies
    if current_index >= len(list_of_inconsistencies):
        log.info("Completed iteration %d. repair_status_array=%s",
                 iteration_count, repair_status_array)
        # Stop if the repair status array is unchanged from the previous iteration
        if repair_status_array == prev_repair_status_array:
            log.info("Repair status unchanged from previous iteration — no further progress. Exiting.")
            return {"status": "EXIT", "iteration_count": iteration_count,
                    "repair_status_array": repair_status_array}
        else:
            # Save current status as previous, start a new pass
            prev_repair_status_array = list(repair_status_array)
            iteration_count += 1
            current_index = 0
            log.info("Starting iteration %d.", iteration_count)

    message = list_of_inconsistencies[current_index]
    log.info("Manager dispatching query [%d/%d] (iteration %d): %s",
             current_index + 1, len(list_of_inconsistencies), iteration_count, message)
    return {
        "status": "Processing",
        "query": message,
        "cycle_count": 0,
        "current_index": current_index + 1,
        "iteration_count": iteration_count,
        "repair_status_array": repair_status_array,
        "prev_repair_status_array": prev_repair_status_array
    }


def check_manager_status(state: agent_state) -> Literal[END, "retrieve"]:
    status = state["status"]
    if status == "EXIT":
        log.info("Manager status EXIT — finishing agent run.")
        return END
    else:
        log.debug("Manager status Processing — routing to retrieve.")
        return "retrieve"
    
    

def evaluate_retrieval_results(state: agent_state) -> Literal["manager", "generate_repairs"]:
    result_count = len(state["results"])
    if result_count == 0:
        log.info("No pattern found in graph — skipping repair, returning to manager.")
        return "manager"
    else:
        log.info("Pattern confirmed (%d result(s)) — routing to generate_repairs.", result_count)
        return "generate_repairs"

def verify_repairs(state: agent_state) -> Literal["manager", "generate_repairs"]:
    log.info("Verifying repair by re-running inconsistency query...")

    db = GraphDB(state["login_url"], state["login_user"], state["login_password"])
    results = db.run_query(state["query"])
    db.close()

    cycle_count = state.get("cycle_count", 0)
    MAX_CYCLES = 5

    if len(results) == 0:
        log.info("Repair verified — inconsistency no longer found. Returning to manager.")
        return "manager"
    else:
        if cycle_count >= MAX_CYCLES:
            log.warning("Repair incomplete after %d cycles. Giving up on query and moving to next.", cycle_count)
            return "manager"
        else:
            log.warning("Repair incomplete — inconsistency still present (%d rows). Retrying (attempt %d/%d).",
                        len(results), cycle_count + 1, MAX_CYCLES)
            return "generate_repairs"

def is_the_repair_query_correct(query: str, state: agent_state) -> bool:
    """Run EXPLAIN on the query to validate syntax before applying it."""
    explain_query = "EXPLAIN " + query
    db = GraphDB(state["login_url"], state["login_user"], state["login_password"])
    try:
        db.run_query(explain_query)
        log.debug("Syntax check passed for query: %s", query[:120])
        return True
    except CypherSyntaxError as e:
        log.warning("Cypher syntax error in generated repair: %s", e)
        return False
    except ClientError as e:
        log.warning("Client error during syntax check: %s", e)
        return False
    except Exception as e:
        log.warning("Unexpected error during syntax check: %s", e, exc_info=True)
        return False
    finally:
        db.close()
