import config
from generator import Generator
from snapshot_tool import export_snapshot

def main():
    print("=== Creating Normal Graph G ===")
    gen = Generator(config.NEO4J_URI, (config.NEO4J_USERNAME, config.NEO4J_PASSWORD))
    
    # Clear the database first
    gen.clear_database()
    
    # Generate new rules and export them
    print("Generating and exporting rules to 'ontology_final.json'...")
    gen.generate_rules(num_allowed=20, num_disallowed=5)
    gen.export_ontology("ontology_final.json")
    
    # Generate the clean valid graph (Graph G)
    print("Generating clean Graph G...")
    gen.generate_valid_graph(num_nodes=50)
    
    # Close generator
    gen.close()
    
    # Export the snapshot of the clean graph
    snapshot_filename = "snapshot_G.cypher"
    print(f"\nExporting snapshot to {snapshot_filename}...")
    export_snapshot(snapshot_filename)
    
    print("\nGraph G successfully created and snapshotted!")

if __name__ == "__main__":
    main()
