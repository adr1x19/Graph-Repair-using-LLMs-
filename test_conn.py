from neo4j import GraphDatabase

def test_conn(uri, user, password):
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        print(f"Success for {uri}")
        driver.close()
    except Exception as e:
        print(f"Failed for {uri}: {e}")

# Old
test_conn("neo4j+s://438810fd.databases.neo4j.io", "438810fd", "FUm3Xh3NR-gY2KYlopzpXkragz6v9g4r-ZO_-djsWA8")
# New
test_conn("neo4j+s://9738bd7b.databases.neo4j.io", "neo4j", "JMOdIBduJdKFNl560eV6CTVWlpYE0iklAstPv7DuDjs")
