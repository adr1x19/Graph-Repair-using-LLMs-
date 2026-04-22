import random
from datetime import date, timedelta
import config

class Generator:
    def __init__(self, db, ontology):
        self.db = db
        self.ontology = ontology

    def generate_valid_graph(self, num_nodes=None):
        if num_nodes is None:
            num_nodes = config.NUM_NODES
            
        self.db.run_query("MATCH (n) DETACH DELETE n")
        print("Creating indexes...")
        for i in range(1, config.NUM_NODE_TYPES + 1):
            self.db.run_query(f"CREATE INDEX IF NOT EXISTS FOR (n:N{i}) ON (n.id)")
            
        print(f"Created nodes with Native Date attributes...")
        
        needs_date = set()
        for src_type, rule in self.ontology.neighborhood_rules.items():
            if rule["type"] == "temporal":
                needs_date.add(src_type)        
                needs_date.add(rule["target"])
        
        needs_prop_x = set()
        if self.ontology.property_constraint:
            needs_prop_x.add(self.ontology.property_constraint["node_type"])
        
        node_ids = []
        for i in range(num_nodes):
            n_type = f"N{random.randint(1, config.NUM_NODE_TYPES)}"
            uid = f"node_{i}"
            
            props_dict={"id":uid}
            
            if n_type in needs_date:
                start_dt = date.fromisoformat(config.START_DATE)
                end_dt = date.fromisoformat(config.END_DATE)
                delta = end_dt - start_dt
                random_days = random.randint(0, delta.days)
                random_date = start_dt + timedelta(days=random_days)
                props_dict["date_val"] = random_date
               
            if n_type in needs_prop_x:
                limit = self.ontology.property_constraint["threshold"]
                x_val = random.randint(limit + 1, 100)
                props_dict["x"] = x_val

            self.db.run_query(f"CREATE (n:{n_type} $props)", params={"props": props_dict}) 
            
            node_ids.append((uid, n_type))

        global_neighbors = {uid: set() for uid, _ in node_ids}

        print("connecting nodes via edges...")
        outer_nodes = list(node_ids)
        for src_id, src_type in outer_nodes:
            max_degree_limit = random.randint(*config.MAX_DEGREE_LIMIT_RANGE)
            exclusive_forbidden = set()
            exclusive_rule = None
            dependency_rule = None 
            temporal_rule = None
            
            if src_type in self.ontology.neighborhood_rules:
                rule = self.ontology.neighborhood_rules[src_type]
                if rule["type"] == "max_degree":
                    max_degree_limit = rule["limit"]
                elif rule["type"] == "exclusive":
                    exclusive_rule = rule
                elif rule["type"] == "dependency":
                    dependency_rule = rule
                elif rule["type"] == "temporal":
                    temporal_rule = rule

            connections_made = 0
            inner_targets = list(node_ids)
            random.shuffle(inner_targets)
            
            for tgt_id, tgt_type in inner_targets:
                if src_id == tgt_id: continue
                if connections_made >= max_degree_limit: break
                if tgt_type in exclusive_forbidden: continue

                target_is_willing = True
                if tgt_type in self.ontology.neighborhood_rules:
                    tgt_rule = self.ontology.neighborhood_rules[tgt_type]
                    if tgt_rule["type"] == "exclusive":
                        pair = tgt_rule["conflict_pair"] 
                        if src_type in pair:
                            enemy = pair[1] if src_type == pair[0] else pair[0]
                            if enemy in global_neighbors[tgt_id]:
                                target_is_willing = False 

                if not target_is_willing: continue
                
                possible_rels = [r for (s, r, t) in self.ontology.allowed_patterns 
                                 if s == src_type and t == tgt_type]
                
                if possible_rels and random.random() < config.RELATION_CREATION_PROBABILITY:
                    r_type = random.choice(possible_rels)
                    
                    if temporal_rule and tgt_type == temporal_rule["target"] and r_type == temporal_rule["rel_type"]:
                        self.db.run_query(f"""
                            MATCH (a:{src_type} {{id: '{src_id}'}})
                            MATCH (b:{tgt_type} {{id: '{tgt_id}'}})
                            WHERE a.date_val <= b.date_val
                            SET a.date_val = b.date_val + duration('P1D')
                        """)
                        
                        self.db.run_query(f"""
                            MATCH (a:{src_type} {{id: '{src_id}'}})
                            MATCH (b:{tgt_type} {{id: '{tgt_id}'}})
                            MERGE (a)-[:{r_type} {{A1: 'active'}}]->(b)
                        """)
                    else:
                        self.db.run_query(f"""
                            MATCH (a:{src_type} {{id: '{src_id}'}})
                            MATCH (b:{tgt_type} {{id: '{tgt_id}'}})
                            MERGE (a)-[:{r_type}]->(b)
                        """)

                    connections_made += 1
                    global_neighbors[src_id].add(tgt_type)
                    global_neighbors[tgt_id].add(src_type)
                    
                    if exclusive_rule and tgt_type in exclusive_rule["conflict_pair"]:
                        pair = exclusive_rule["conflict_pair"]
                        other = pair[1] if tgt_type == pair[0] else pair[0]
                        exclusive_forbidden.add(other)
                    
                    if dependency_rule and tgt_type == dependency_rule["trigger"]:
                        req_type = dependency_rule["required"]
                        req_rel = dependency_rule["rel_type"]
                        self.db.run_query(f"""
                            MATCH (src {{id: '{src_id}'}})
                            MATCH (partner:{req_type}) WHERE partner.id <> src.id
                            WITH src, partner LIMIT 1
                            MERGE (src)-[:{req_rel}]->(partner)
                        """)
                        global_neighbors[src_id].add(req_type)
