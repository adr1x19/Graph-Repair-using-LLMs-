from neo4j import GraphDatabase
import logging 

class GraphDB:
    def __init__(self, url, user, password):
        try:
            self.driver = GraphDatabase.driver(
                url, 
                auth=(user, password),
                connection_timeout=120.0,
                keep_alive=True,
                max_connection_lifetime=3600
            )
            print("The Graph Database has been started.")

        except Exception as e:
            logging.error("Failed Connection to Neo4j")


    def close(self):
        logging.info("Driver closed.")
        self.driver.close()
        print("\nDriver Closed.")

    def run_query(self, query, params={}):
        if not query or not query.strip():
            logging.warning("Attempted to run an empty query; execution skipped.")
            return []
            
        with self.driver.session() as session:
            result = session.run(query, params)
            return [record.data() for record in result]