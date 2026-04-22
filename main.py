import json
import config
from database import GraphDB
from ontology import OntologyGenerator
from generator import Generator 
from injector import ViolationInjector
from evaluator import TailoredEvaluator 
from langgraph.graph import StateGraph, START
from state import agent_state
import nodes
from snapshot_tool import export_snapshot

def build_repair_app():
    workflow = StateGraph(agent_state)
    
    workflow.add_node("extract_schema", nodes.extract_schema)
    workflow.add_node("manager", nodes.manager)
    workflow.add_node("retrieve", nodes.retrieve)
    workflow.add_node("generate_repairs", nodes.generate_repairs)
    workflow.add_node("apply", nodes.apply)
    
    workflow.add_edge(START, "extract_schema")
    workflow.add_edge("extract_schema", "manager")
    
    # Add Conditional Edges
    workflow.add_conditional_edges(
        "manager",
        nodes.check_manager_status,
    )
    workflow.add_conditional_edges(
        "retrieve",
        nodes.evaluate_retrieval_results,
    )
    workflow.add_edge("generate_repairs", "apply")
    workflow.add_conditional_edges(
        "apply",
        nodes.verify_repairs
    )

    return workflow.compile()

def run_experiment():
    db = GraphDB(config.NEO4J_URI, config.NEO4J_USERNAME, config.NEO4J_PASSWORD)
    
    print("Generating Graph Rules...")
    onto = OntologyGenerator()
    onto.generate_rules(num_allowed=20, num_disallowed=5)
    onto.export_ontology("ontology_final.json")
    
    evaluator = TailoredEvaluator(config.NEO4J_URI, config.NEO4J_USERNAME, config.NEO4J_PASSWORD, "ontology_final.json")

    print("Generating Clean Graph...")
    gen = Generator(db, onto)
    gen.generate_valid_graph(num_nodes=50)
    snap_gold = evaluator.fetch_snapshot()
    print("Exporting snapshot of clean graph...")
    export_snapshot("snapshot_gold.cypher")

    print("Injecting Violations...")
    injector = ViolationInjector(db, onto)
    injector.inject_violations()
    snap_messy = evaluator.fetch_snapshot()
    print("Exporting snapshot of messy graph...")
    export_snapshot("snapshot_messy.cypher")

    print("Loading inconsistencies.txt...")
    list_of_inconsistencies = []
    try:
        with open("inconsistencies.txt", "r") as file:
            list_of_inconsistencies = [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        print("Error: inconsistencies.txt not found!")

    print("Starting Agent Repair...")
    app = build_repair_app()
    
    initial_state = {
        "login_url": config.NEO4J_URI,
        "login_user": config.NEO4J_USERNAME,
        "login_password": config.NEO4J_PASSWORD,
        "list_of_inconsistencies": list_of_inconsistencies, 
        "database_description": "",
        "total_tokens": 0,
        "results": [],
        "query": "",
        "status": "",
        "cycle_count": 0
    }
    
    final_state = app.invoke(initial_state)

    print("Exporting snapshot of repaired graph...")
    export_snapshot("snapshot_repaired.cypher")

    print("Calculating Metrics...")
    results = evaluator.evaluate(snap_gold, snap_messy, final_state.get("total_tokens", 0))
    
    print("\n--- EXPERIMENT RESULTS ---")
    print(json.dumps(results, indent=4))
    
    db.close()

if __name__ == "__main__":
    print(f"Using Model: {config.OLLAMA_MODEL}")
    run_experiment()
