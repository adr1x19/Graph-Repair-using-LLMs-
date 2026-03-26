import config
from generator import Generator
from snapshot_tool import export_snapshot

def main():
    print("=== Injecting Inconsistencies to Create Graph G_in ===")
    gen = Generator(config.NEO4J_URI, (config.NEO4J_USERNAME, config.NEO4J_PASSWORD))
    
    # Load previously generated rules from ontology_final.json
    try:
        gen.load_ontology("ontology_final.json")
        print("Successfully loaded 'ontology_final.json'")
    except FileNotFoundError:
        print("Error: 'ontology_final.json' not found. Please run create_G.py first!")
        gen.close()
        return

    # Inject the violations to create the messy graph G_in
    print("Injecting violations...")
    gen.inject_violations()
    
    # Close generator
    gen.close()
    
    # Export the snapshot of the messy graph
    snapshot_filename = "snapshot_G_in.cypher"
    print(f"\nExporting snapshot to {snapshot_filename}...")
    export_snapshot(snapshot_filename)
    
    print("\nGraph G_in successfully created and snapshotted!")

if __name__ == "__main__":
    main()
