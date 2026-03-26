
import config
from generator import Generator
from snapshot_tool import export_snapshot

def main():
    print("=== Injecting EVERY Type of Inconsistency (Graph G_all_in) ===")
    gen = Generator(config.NEO4J_URI, (config.NEO4J_USERNAME, config.NEO4J_PASSWORD))
    
    # Load previously generated rules from ontology_final.json
    try:
        gen.load_ontology("ontology_final.json")
        print("Successfully loaded 'ontology_final.json'")
    except FileNotFoundError:
        print("Error: 'ontology_final.json' not found. Please run create_G.py first!")
        gen.close()
        return

    # Deterministically inject every violation type
    print("Injecting all violation types...")
    gen.inject_violations()
    
    # Close generator
    gen.close()
    
    # Export the snapshot of the messy graph
    snapshot_filename = "snapshot_G_all_in.cypher"
    print(f"\nExporting snapshot to {snapshot_filename}...")
    export_snapshot(snapshot_filename)
    
    print("\nGraph G_all_in successfully created and snapshotted!")

if __name__ == "__main__":
    main()
