import json
import os
import config
import logging
from datetime import datetime
from generator import Generator
from evaluator import TailoredEvaluator
from langgraph.graph import StateGraph, START
from state import agent_state
import nodes
from snapshot_tool import export_snapshot, restore_snapshot


MODEL_LIST = [
    "gemma3:27b",
    "gpt-oss:20b",
    "qwen3.5:27b",
]


NUM_NODES = 10000
NUM_ALLOWED = 1000
NUM_DISALLOWED = 100


# ── Set once in main() ──────────────────────────────────────────────────────
LOG_DIR = None


def setup_logging(timestamp: str) -> str:
    """
    Configure root logger with a single FileHandler only.
    Nothing is printed to the terminal — all output goes to LOG_DIR.
    Returns the full path to the log file.
    """
    log_filename = os.path.join(LOG_DIR, f"benchmark_{timestamp}.log")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    
    root.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

   
    fh = logging.FileHandler(log_filename, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    
    return log_filename


log = logging.getLogger("benchmark")



def build_repair_app():
    """Build the LangGraph repair agent."""
    log.debug("Building repair agent graph...")
    workflow = StateGraph(agent_state)

    workflow.add_node("extract_schema", nodes.extract_schema)
    workflow.add_node("manager", nodes.manager)
    workflow.add_node("retrieve", nodes.retrieve)
    workflow.add_node("generate_repairs", nodes.generate_repairs)
    workflow.add_node("apply", nodes.apply)

    workflow.add_edge(START, "extract_schema")
    workflow.add_edge("extract_schema", "manager")

    workflow.add_conditional_edges("manager", nodes.check_manager_status)
    workflow.add_conditional_edges("retrieve", nodes.evaluate_retrieval_results)
    workflow.add_edge("generate_repairs", "apply")
    workflow.add_conditional_edges("apply", nodes.verify_repairs)

    log.debug("Repair agent graph compiled.")
    return workflow.compile()


def generate_and_snapshot():
    """
    Generate clean graph → inject violations → snapshot both states.
    Returns (snap_gold, snap_messy, list_of_inconsistencies, graph_metrics).
    """
    log.info("PHASE 1: Generating Graph & Injecting Inconsistencies")

    gen = Generator(config.NEO4J_URI, (config.NEO4J_USERNAME, config.NEO4J_PASSWORD))

    # ── ontology goes into the run folder ──
    ontology_path = os.path.join(LOG_DIR, "ontology_final.json")

    log.info("[1/6] Generating rules (allowed=%d, disallowed=%d)...",
             NUM_ALLOWED, NUM_DISALLOWED)
    gen.generate_rules(num_allowed=NUM_ALLOWED, num_disallowed=NUM_DISALLOWED)
    gen.export_ontology(ontology_path)
    log.debug("Ontology exported to %s", ontology_path)


    evaluator = TailoredEvaluator(
        config.NEO4J_URI, config.NEO4J_USERNAME, config.NEO4J_PASSWORD,
        ontology_path
    )

   
    log.info("[2/6] Generating clean graph G (num_nodes=%d)...", NUM_NODES)
    gen.generate_valid_graph(num_nodes=NUM_NODES)
    snap_gold = evaluator.fetch_snapshot()
    log.info("Clean graph: %d nodes, %d edges",
             len(snap_gold["nodes"]), len(snap_gold["edges"]))

    log.info("[3/6] Exporting snapshot_gold.cypher...")
    export_snapshot(os.path.join(LOG_DIR, "snapshot_gold.cypher"))

   
    log.info("[4/6] Injecting violations...")
    gen.inject_violations()
    snap_messy = evaluator.fetch_snapshot()
    log.info("Messy graph: %d nodes, %d edges",
             len(snap_messy["nodes"]), len(snap_messy["edges"]))

    log.info("[5/6] Exporting snapshot_messy.cypher...")
    export_snapshot(os.path.join(LOG_DIR, "snapshot_messy.cypher"))

    log.info("[6/6] Reading inconsistencies.txt...")
    list_of_inconsistencies = []
    try:
        with open("inconsistencies.txt", "r") as f:
            list_of_inconsistencies = [line.strip() for line in f if line.strip()]
        log.info("Loaded %d inconsistency queries:", len(list_of_inconsistencies))
        for i, q in enumerate(list_of_inconsistencies, 1):
            log.debug("  [%d] %s", i, q)
    except FileNotFoundError:
        log.error("inconsistencies.txt not found!")
    log.info("Calculating graph metrics for messy graph...")
    graph_metrics = evaluator.get_graph_metrics("messy_graph",
                                                 ontology_file=ontology_path)
    log.info("Graph metrics: %s", graph_metrics)

    gen.close()

    log.info("Phase 1 complete — %d inconsistencies to repair.", len(list_of_inconsistencies))
    return snap_gold, snap_messy, list_of_inconsistencies, graph_metrics




def run_model(model_name, snap_gold, snap_messy, list_of_inconsistencies):
    """
    Restore messy graph → run agent with given model → evaluate.
    Returns the results dict.
    """
    model_log = logging.getLogger(f"benchmark.model.{model_name}")
    model_log.info("Starting run for model: %s", model_name)

    
    config.OLLAMA_MODEL = model_name
    model_log.debug("config.OLLAMA_MODEL set to: %s", model_name)

    
    model_log.info("[1/4] Restoring messy graph from snapshot_messy.cypher...")
    restore_snapshot(os.path.join(LOG_DIR, "snapshot_messy.cypher"))


    model_log.info("[2/4] Building and invoking repair agent...")
    app = build_repair_app()

    inconsistencies_copy = list(list_of_inconsistencies)
    model_log.debug("Inconsistencies to process: %s", inconsistencies_copy)

    initial_state = {
        "login_url": config.NEO4J_URI,
        "login_user": config.NEO4J_USERNAME,
        "login_password": config.NEO4J_PASSWORD,
        "list_of_inconsistencies": inconsistencies_copy,
        "database_description": "",
        "total_tokens": 0,
        "results": [],
        "query": "",
        "status": "",
        "cycle_count": 0,
        "iteration_count": 0,
        "current_index": 0,
        "repair_status_array": [False] * len(inconsistencies_copy),
        "prev_repair_status_array": []
    }

    model_log.debug("Initial agent state: %s", {k: v for k, v in initial_state.items()
                                                  if k not in ("login_password",)})

    final_state = app.invoke(initial_state)
    model_log.info("Agent finished. Cycles: %d, Tokens: %d",
                   final_state.get("cycle_count", 0),
                   final_state.get("total_tokens", 0))

 
    safe_name = model_name.replace(":", "_").replace("/", "_")
    repaired_filename = os.path.join(LOG_DIR, f"snapshot_repaired_{safe_name}.cypher")
    model_log.info("[3/4] Exporting repaired snapshot: %s", repaired_filename)
    export_snapshot(repaired_filename)

    ontology_path = os.path.join(LOG_DIR, "ontology_final.json")
    model_log.info("[4/4] Evaluating...")
    evaluator = TailoredEvaluator(
        config.NEO4J_URI, config.NEO4J_USERNAME, config.NEO4J_PASSWORD,
        ontology_path
    )
    results = evaluator.evaluate(
        snap_gold, snap_messy,
        final_state.get("total_tokens", 0)
    )
    results["model"] = model_name
    results["cycles"] = final_state.get("cycle_count", 0)
    results["total_tokens"] = final_state.get("total_tokens", 0)

    model_log.info("Results for %s:\n%s", model_name, json.dumps(results, indent=4))
    return results




def log_comparison_table(all_results):
    """Log a comparison table of all model results."""
    metrics = [
        "Validity", "Fidelity Score (0-1)", "Normalized GED (0-1)",
        "Raw GED Remaining", "Minimality (Repair Cost)",
        "Optimality Ratio", "Efficiency (Tokens/Fix)",
        "cycles", "total_tokens"
    ]

    header = f"{'Metric':<30}"
    for r in all_results:
        header += f" | {r['model']:>18}"

    separator = "-" * len(header)
    rows = ["\n" + "=" * 80, "BENCHMARK COMPARISON TABLE", "=" * 80, header, separator]

    for metric in metrics:
        row = f"{metric:<30}"
        for r in all_results:
            val = r.get(metric, "N/A")
            if isinstance(val, float):
                row += f" | {val:>18.4f}"
            elif isinstance(val, int):
                row += f" | {val:>18d}"
            else:
                row += f" | {str(val):>18}"
        rows.append(row)

    rows.append("=" * 80)
    table_str = "\n".join(rows)

    log.info(table_str)




def main():
    global LOG_DIR

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── create the timestamped run folder at the original LOG_DIR location ──
    LOG_DIR = f"/scratch/hrishikesh/users/aadi_2023A7PS0130H/logsfiles/benchmark_{timestamp}"
    os.makedirs(LOG_DIR, exist_ok=True)

    log_filename = setup_logging(timestamp)


    log.info("Timestamp  : %s", timestamp)
    log.info("Run folder : %s", LOG_DIR)
    log.info("Log file   : %s", log_filename)
    log.info("Models (%d): %s", len(MODEL_LIST), ", ".join(MODEL_LIST))
    log.info("Graph params: nodes=%d, allowed=%d, disallowed=%d",
             NUM_NODES, NUM_ALLOWED, NUM_DISALLOWED)

    snap_gold, snap_messy, list_of_inconsistencies, graph_metrics = generate_and_snapshot()


    all_results = []
    for i, model in enumerate(MODEL_LIST, 1):
        log.info("RUNNING MODEL %d/%d: %s", i, len(MODEL_LIST), model)
        try:
            results = run_model(model, snap_gold, snap_messy, list_of_inconsistencies)
            all_results.append(results)
        except Exception as e:
            log.error("ERROR running model %s: %s", model, e, exc_info=True)
            all_results.append({"model": model, "error": str(e)})


    log_comparison_table(all_results)
    output_file = os.path.join(LOG_DIR, f"benchmark_results_{timestamp}.json")
    
    payload = {
        "timestamp": timestamp,
        "run_folder": LOG_DIR,
        "log_file": log_filename,
        "models": MODEL_LIST,
        "graph_params": {
            "num_nodes": NUM_NODES,
            "num_allowed": NUM_ALLOWED,
            "num_disallowed": NUM_DISALLOWED,
            "num_inconsistencies": len(list_of_inconsistencies)
        },
        "graph_metrics": graph_metrics,
        "results": all_results
    }
    with open(output_file, "w") as f:
        json.dump(payload, f, indent=4)

    log.info("Results JSON saved to: %s", output_file)
    log.info("Log saved to: %s", log_filename)
    log.info("All outputs saved in: %s", LOG_DIR)
    log.info("Benchmark complete!")


if __name__ == "__main__":
    main()
