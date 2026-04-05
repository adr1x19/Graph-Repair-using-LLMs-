import random
import json
from neo4j import GraphDatabase
from datetime import date, timedelta

class Generator:
    def __init__(self, uri, auth):
        self.driver = GraphDatabase.driver(uri, auth=auth)
        self.num_node_types = 5  
        self.num_rel_types = 4   
        
        self.allowed_patterns = set()
        self.disallowed_patterns = set()
        self.neighborhood_rules = {} 
        self.property_constraint = None

    def close(self):
        self.driver.close()

    def clear_database(self):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    # --- 1. GENERATE RULES ---
    def generate_rules(self, num_allowed=20, num_disallowed=5):
        all_node_types = [f"N{i}" for i in range(1, self.num_node_types + 1)]
        all_rel_types = [f"R{i}" for i in range(1, self.num_rel_types + 1)]
        
        universe = set()
        for src in all_node_types:
            for tgt in all_node_types:
                for rel in all_rel_types:
                    universe.add((src, rel, tgt))
        
        self.allowed_patterns = set(random.sample(list(universe), num_allowed))
        remaining = universe - self.allowed_patterns
        self.disallowed_patterns = set(random.sample(list(remaining), num_disallowed))
        
        
        
        # single node property check
        active_types = set()
        for (s, r, t) in self.allowed_patterns:
            active_types.add(s)
            active_types.add(t)
        
        if active_types:
            target_type = random.choice(list(active_types))
            threshold_val = random.randint(30, 70)
            self.property_constraint = {
                "node_type": target_type,
                "threshold": threshold_val
            }

        # Neighborhood Constraints
        for n_type in all_node_types:
            rand_val = random.random()
            
            # 1. Max Degree
            if rand_val < 0.2:
                self.neighborhood_rules[n_type] = {
                    "type": "max_degree",
                    "limit": random.randint(1, 5),
                    "rel_type": random.choice(all_rel_types)
                }
            
            # 2. Exclusive
            elif rand_val < 0.5:
                others = [t for t in all_node_types if t != n_type]
                if len(others) >= 2:
                    self.neighborhood_rules[n_type] = {
                        "type": "exclusive",
                        "conflict_pair": random.sample(others, 2), 
                        "rel_type": random.choice(all_rel_types)
                    }

            # 3. Dependency
            elif rand_val < 0.75:
                others = [t for t in all_node_types if t != n_type]
                if len(others) >= 2:
                    pair = random.sample(others, 2)
                    self.neighborhood_rules[n_type] = {
                        "type": "dependency",
                        "trigger": pair[0],   
                        "required": pair[1],  
                        "rel_type": random.choice(all_rel_types)
                    }
            
            # 4. TEMPORAL RULE (Native Date)
            else:
                others = [t for t in all_node_types if t != n_type]
                if others:
                    target = random.choice(others)
                    self.neighborhood_rules[n_type] = {
                        "type": "temporal",
                        "target": target,
                        "rel_type": random.choice(all_rel_types) 
                    }

    # --- 2. GENERATE VALID GRAPH ---
    def generate_valid_graph(self, num_nodes=80):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print(f"Created nodes with Native Date attributes...")
            
            # --- STEP A: IDENTIFY WHO NEEDS PROPERTIES ---
            # 1. Who needs a Date? (Source and Target of Temporal Rules)
            needs_date = set()
            for src_type, rule in self.neighborhood_rules.items():
                if rule["type"] == "temporal":
                    needs_date.add(src_type)       # The Source needs a date
                    needs_date.add(rule["target"]) # The Target needs a date
            
            # 2. Who needs Property X? (Only the specific type in the constraint)
            needs_prop_x = set()
            if self.property_constraint:
                needs_prop_x.add(self.property_constraint["node_type"])
            
            node_ids = []
            for i in range(num_nodes):
                n_type = f"N{random.randint(1, self.num_node_types)}"
                uid = f"node_{i}"
                
                props = [f"id: '{uid}'"]
                
                # Generate YYYY-MM-DD string
                if n_type in needs_date:
                    start_dt = date(2000, 1, 1)
                    end_dt = date(2023, 12, 31)
                    delta = end_dt - start_dt
                    random_days = random.randint(0, delta.days)
                    random_date = start_dt + timedelta(days=random_days)
                    date_str = random_date.strftime("%Y-%m-%d")
                    props.append(f"date_val: date('{date_str}')")
                   
                if n_type in needs_prop_x:
                    limit = self.property_constraint["threshold"]
                    x_val = random.randint(limit + 1, 100) # Valid value
                    props.append(f"x: {x_val}")

                # Join properties with commas and create node
                props_str = ", ".join(props)
                session.run(f"CREATE (n:{n_type} {{ {props_str} }})")
                
                node_ids.append((uid, n_type))

            global_neighbors = {uid: set() for uid, _ in node_ids}

            print("connecting nodes via edges...")
            for src_id, src_type in node_ids:
                
                max_degree_limit = 999
                exclusive_forbidden = set()
                exclusive_rule = None
                dependency_rule = None 
                temporal_rule = None
                
                if src_type in self.neighborhood_rules:
                    rule = self.neighborhood_rules[src_type]
                    if rule["type"] == "max_degree":
                        max_degree_limit = rule["limit"]
                    elif rule["type"] == "exclusive":
                        exclusive_rule = rule
                    elif rule["type"] == "dependency":
                        dependency_rule = rule
                    elif rule["type"] == "temporal":
                        temporal_rule = rule

                connections_made = 0
                random.shuffle(node_ids)
                
                for tgt_id, tgt_type in node_ids:
                    if src_id == tgt_id: continue
                    if connections_made >= max_degree_limit: break
                    if tgt_type in exclusive_forbidden: continue

                    target_is_willing = True
                    if tgt_type in self.neighborhood_rules:
                        tgt_rule = self.neighborhood_rules[tgt_type]
                        if tgt_rule["type"] == "exclusive":
                            pair = tgt_rule["conflict_pair"] 
                            if src_type in pair:
                                enemy = pair[1] if src_type == pair[0] else pair[0]
                                if enemy in global_neighbors[tgt_id]:
                                    target_is_willing = False 

                    if not target_is_willing: continue
                    
                    possible_rels = [r for (s, r, t) in self.allowed_patterns 
                                     if s == src_type and t == tgt_type]
                    
                    if possible_rels and random.random() < 0.2:
                        r_type = random.choice(possible_rels)
                        
                        # --- TEMPORAL CONSTRAINT LOGIC (Native) ---
                        if temporal_rule and tgt_type == temporal_rule["target"] and r_type == temporal_rule["rel_type"]:
                            
                            # Clean Logic: Just compare a.date_val > b.date_val directly
                            session.run(f"""
                                MATCH (a {{id: '{src_id}'}}), (b {{id: '{tgt_id}'}})
                                WHERE a.date_val <= b.date_val
                                // Fix: Make A one day after B
                                SET a.date_val = b.date_val + duration('P1D')
                            """)
                            
                            #  Edge with A1 attribute only if temporal rule is active otherwise no edge attribute given
                            session.run(f"""
                                MATCH (a {{id: '{src_id}'}}), (b {{id: '{tgt_id}'}})
                                MERGE (a)-[:{r_type} {{A1: 'active'}}]->(b)
                            """)
                        else:        # otherwise case of temporal
                            session.run(f"""
                                MATCH (a {{id: '{src_id}'}}), (b {{id: '{tgt_id}'}})
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
                            session.run(f"""
                                MATCH (src {{id: '{src_id}'}})
                                MATCH (partner:{req_type}) WHERE partner.id <> src.id
                                WITH src, partner LIMIT 1
                                MERGE (src)-[:{req_rel}]->(partner)
                            """)
                            global_neighbors[src_id].add(req_type)

    # --- 3. INJECT EXACTLY 1 OF EACH VIOLATION TYPE ---
    def inject_violations(self):
        print("Injecting exactly 1 of every possible violation type...")
        
        violation_types = ["triple", "cardinality", "exclusive", "dependency", "temporal", "property_x"]
        
        with self.driver.session() as session:
            success_count = 0
            
            with open("inconsistencies.txt", "w") as file:
                for v_type in violation_types:
                    result = None
                    inconsistency_query = ""

                    if v_type == "triple" and self.disallowed_patterns:
                        src, r, tgt = random.choice(list(self.disallowed_patterns))
                        result = session.run(f"MATCH (a:{src}), (b:{tgt}) WHERE a.id <> b.id WITH a,b LIMIT 1 MERGE (a)-[:{r}]->(b) RETURN a")
                        inconsistency_query = f"MATCH (n1:{src})-[r:{r}]->(n2:{tgt}) RETURN n1, r, n2"

                    elif v_type == "cardinality":
                        cands = [k for k, v in self.neighborhood_rules.items() if v["type"] == "max_degree"]
                        if cands:
                            v = random.choice(cands)
                            rule = self.neighborhood_rules[v]
                            overflow = rule["limit"] + 2
                            result = session.run(f"""
                                 MATCH (a:{v}) WITH a LIMIT 1 MATCH (b) WHERE a <> b
                                 WITH a, collect(b)[0..{overflow}] as chosen UNWIND chosen AS b
                                 MERGE (a)-[:{rule['rel_type']}]->(b)  RETURN a
                            """)
                            inconsistency_query = f"MATCH (n1:{v})-[r:{rule['rel_type']}]->(n2) RETURN n1, r, n2"

                    elif v_type == "exclusive":
                        cands = [k for k,v in self.neighborhood_rules.items() if v["type"]=="exclusive"]
                        if cands:
                            v = random.choice(cands)
                            rule = self.neighborhood_rules[v]
                            p1, p2 = rule["conflict_pair"]
                            result = session.run(f"""
                                MATCH (a:{v}) WITH a LIMIT 1 MATCH (t1:{p1}), (t2:{p2}) WITH a,t1,t2 LIMIT 1 
                                MERGE (a)-[:{rule['rel_type']}]->(t1) MERGE (a)-[:{rule['rel_type']}]->(t2)  RETURN a
                            """)
                            inconsistency_query = f"MATCH (n1:{v})-[r1:{rule['rel_type']}]->(n2:{p1}), (n1)-[r2:{rule['rel_type']}]->(n3:{p2}) RETURN n1, r1, n2, r2, n3"

                    elif v_type == "dependency":
                        cands = [k for k,v in self.neighborhood_rules.items() if v["type"]=="dependency"]
                        if cands:
                            v_type_node = random.choice(cands)
                            rule = self.neighborhood_rules[v_type_node]
                            result = session.run(f"""
                                MATCH (a:{v_type_node}), (b:{rule['trigger']}) WHERE a.id <> b.id WITH a, b LIMIT 1
                                MERGE (a)-[:{rule['rel_type']}]->(b) WITH a
                                OPTIONAL MATCH (a)-[r]->(c:{rule['required']}) DELETE r
                                    RETURN a
                            """)
                            inconsistency_query = f"MATCH (n1:{v_type_node})-[r:{rule['rel_type']}]->(n2:{rule['trigger']}) RETURN n1, r, n2"

                    elif v_type == "temporal":
                        result = session.run(f"""
                            MATCH (a)-[r {{A1: 'active'}}]->(b)
                            WITH a, b LIMIT 1
                            SET a.date_val = b.date_val - duration('P10D')
                             RETURN a
                        """)
                        inconsistency_query = f"MATCH (a)-[r {{A1: 'active'}}]->(b) WHERE a.date_val <= b.date_val RETURN a, r, b"
                        
                    elif v_type == "property_x" and self.property_constraint:
                        target_type = self.property_constraint["node_type"]
                        threshold = self.property_constraint["threshold"]
                        result = session.run(f"""
                            MATCH (n:{target_type})
                            WHERE n.x > {threshold}
                            WITH n LIMIT 1
                            SET n.x = {threshold} - 10
                                RETURN n
                        """)
                        inconsistency_query = f"MATCH (n:{target_type}) WHERE n.x <= {threshold} RETURN n"

                    if result and result.peek():
                        print(f"  [Success] Injected {v_type} violation.")
                        file.write(f"{inconsistency_query}\n")
                        success_count += 1
                    else:
                        print(f"  [Failed] Could not inject {v_type} violation (graph preconditions not met).")
                        
            print(f"Finished. Total violations injected: {success_count}/6")

    def export_ontology(self, filename="ontology_final.json"):
        data = {
            "triples": {
                "allowed": [list(p) for p in self.allowed_patterns],
                "disallowed": [list(p) for p in self.disallowed_patterns]
            },
            "neighborhood_constraints": self.neighborhood_rules,
            "property_constraint": self.property_constraint
        }
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

    def load_ontology(self, filename="ontology_final.json"):
        with open(filename, "r") as f:
            data = json.load(f)
        self.allowed_patterns = set(tuple(p) for p in data["triples"]["allowed"])
        self.disallowed_patterns = set(tuple(p) for p in data["triples"]["disallowed"])
        self.neighborhood_rules = data["neighborhood_constraints"]
        self.property_constraint = data.get("property_constraint", None)

if __name__ == "__main__":
    gen = Generator("neo4j+s://438810fd.databases.neo4j.io", ("438810fd", "FUm3Xh3NR-gY2KYlopzpXkragz6v9g4r-ZO_-djsWA8"))
    gen.clear_database()
    gen.generate_rules(num_allowed=20, num_disallowed=5)
    gen.generate_valid_graph(num_nodes=50)
    gen.inject_violations()
    gen.export_ontology()
    gen.close()
