import config
from database import GraphDB
from datetime import datetime

def export_snapshot(output_filename="snapshot.cypher"):
    db = GraphDB(config.NEO4J_URI, config.NEO4J_USERNAME, config.NEO4J_PASSWORD)
    
    # We use stream: true so that APOC sends the data back to our Python client
    # instead of trying to write it to the Neo4j server's restricted file system.
    query = """
    CALL apoc.export.cypher.all(null, {
        stream: true,
        format: 'cypher-shell'
    })
    YIELD cypherStatements
    RETURN cypherStatements AS data
    """
    
    print("Extracting database snapshot from Neo4j...")
    
    try:
        results = db.run_query(query)
        if results and len(results) > 0 and 'data' in results[0]:
            snapshot_data = results[0]['data']
            
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write(snapshot_data)
                
            print(f"Snapshot successfully saved to '{output_filename}'.")
            print("You can now use a differencing tool like VS Code or WinMerge to compare this file with other snapshots.")
        else:
            print("No data was returned. Is the database empty?")
    except Exception as e:
        print(f"Error extracting snapshot: {e}")
        print("Note: Ensure the APOC plugin is installed and apoc.export.* procedures are permitted in your Neo4j configuration.")
    finally:
        db.close()

if __name__ == "__main__":
    # Generate a timestamped filename so you can easily compare different states over time
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"snapshot_{timestamp}.cypher"
    
    export_snapshot(filename)
