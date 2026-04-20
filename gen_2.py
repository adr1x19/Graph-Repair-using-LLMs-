import random
import json
import neo4j
from neo4j import GraphDatabase
from datetime import date, timedelta

class Generator:
    def __init__(self, uri, auth):
        self.driver = GraphDatabase.driver(
            uri,
            auth=auth,

        )

        self.num_node_types = 50
        self.num_rel_types = 15

        self.allowed_patterns = set()
        self.disallowed_patterns = set()
        self.neighborhood_rules = {}
        self.property_constraint = None

    def close(self):
        self.driver.close()

    def clear_database(self):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    #                  GENERATE RULES
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



        # single node property check with random threshold [should be greater than threshold, defined later in generation logic]
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

        #                           Neighborhood Constraints
        for n_type in all_node_types:
            rand_val = random.random()       # decides which rule will be forced on current node type

            #  Max Degree     e.g for ENVDEDA ---->   molecule can only have 3 active sites
            if rand_val < 0.2:
                self.neighborhood_rules[n_type] = {
                    "type": "max_degree",
                    "limit": random.randint(1, 5),
                    "rel_type": random.choice(all_rel_types)
                }

     #  Exclusive [ if A->B then A!->C vice verse too]   e.g for ENVDEDA --->A plant cannot live in both the Desert and the Rainforest
            elif rand_val < 0.5:
                others = [t for t in all_node_types if t != n_type]   # list of other n_types than current n_type
                if len(others) >= 2:
                    self.neighborhood_rules[n_type] = {
                        "type": "exclusive",
                        "conflict_pair": random.sample(others, 2),
                        "rel_type": random.choice(all_rel_types)
                    }

     #  Dependency [assymetry b/w trigger & required] e.g. for ENVEDA ---> if entry contain protein P1, it must also contain P2(P2 derivative of P1)
            elif rand_val < 0.75:
                others = [t for t in all_node_types if t != n_type]
                if len(others) >= 2:          #imp because 2 nodes at random are selected for rule
                    pair = random.sample(others, 2)
                    self.neighborhood_rules[n_type] = {
                        "type": "dependency",
                        "trigger": pair[0],
                        "required": pair[1],
                        "rel_type": random.choice(all_rel_types)
                    }

            # TEMPORAL RULE   e.g. for ENVEDA ---->  date mismatches in samples taken and experiments done by scientists
            else:
                others = [t for t in all_node_types if t != n_type]
                if others:
                    target = random.choice(others)
                    self.neighborhood_rules[n_type] = {
                        "type": "temporal",
                        "target": target,
                        "rel_type": random.choice(all_rel_types)
                    }

        # GUARANTEE 1 temporal
        if not any(v["type"] == "temporal" for v in self.neighborhood_rules.values()):

            # Pick a node type not already assigned a rule, or override a random one if all assigned
            # overriding could still select the type which was assigned only once but chances were low so used this logic
            #also guarantee blocks are sequential so logic will keep on assigning rules if it accidently selected the
            #  rule which was assigned only once

            unassigned = [t for t in all_node_types if t not in self.neighborhood_rules]
            fallback_type = random.choice(unassigned if unassigned else all_node_types)

            others = [t for t in all_node_types if t != fallback_type]
            self.neighborhood_rules[fallback_type] = {
                "type": "temporal",
                "target": random.choice(others),
                "rel_type": random.choice(all_rel_types)
            }
            print(f"  [Guaranteed] Assigned temporal rule to {fallback_type}")

        # GUARANTEE 1 dependency
        if not any(v["type"] == "dependency" for v in self.neighborhood_rules.values()):

           #same logic as above guarantees
            unassigned = [t for t in all_node_types if t not in self.neighborhood_rules]
            fallback_type = random.choice(unassigned if unassigned else all_node_types)

            others = [t for t in all_node_types if t != fallback_type]
            pair = random.sample(others, 2)
            self.neighborhood_rules[fallback_type] = {
                "type": "dependency",
                "trigger": pair[0],
                "required": pair[1],
                "rel_type": random.choice(all_rel_types)
            }
            print(f"  [Guaranteed] Assigned dependency rule to {fallback_type}")

        # GUARANTEE max_degree
        if not any(v["type"] == "max_degree" for v in self.neighborhood_rules.values()):

            unassigned = [t for t in all_node_types if t not in self.neighborhood_rules]
            fallback_type = random.choice(unassigned if unassigned else all_node_types)

            self.neighborhood_rules[fallback_type] = {
                "type": "max_degree",
                "limit": random.randint(1, 5),
                "rel_type": random.choice(all_rel_types)
            }
            print(f"  [Guaranteed] Assigned max_degree rule to {fallback_type}")

        # GUARANTEE 1 exclusive
        if not any(v["type"] == "exclusive" for v in self.neighborhood_rules.values()):

            unassigned = [t for t in all_node_types if t not in self.neighborhood_rules]
            fallback_type = random.choice(unassigned if unassigned else all_node_types)

            others = [t for t in all_node_types if t != fallback_type]
            self.neighborhood_rules[fallback_type] = {
                "type": "exclusive",
                "conflict_pair": random.sample(others, 2),
                "rel_type": random.choice(all_rel_types)
            }
            print(f"  [Guaranteed] Assigned exclusive rule to {fallback_type}")

    #  GENERATE VALID GRAPH   valid means a graph with only the rules that we just forced on nodes and rels
    def generate_valid_graph(self, num_nodes=80):

        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")    #have already used cleardb func in main, should remove but though gud practice
            print("Creating indexes...")
            for i in range(1, self.num_node_types + 1):
                session.run(f"CREATE INDEX IF NOT EXISTS FOR (n:N{i}) ON (n.id)")
            print(f"Created nodes with Native Date attributes...")

                                         # A: IDENTIFY WHO NEEDS PROPERTIES

        #  Who needs a Date? -> (Source and Target of Temporal Rules)
            needs_date = set()
            for src_type, rule in self.neighborhood_rules.items():
                if rule["type"] == "temporal":
                    needs_date.add(src_type)
                    needs_date.add(rule["target"])

        # Who needs Property X ->everyone who lies inside property constraints set
            needs_prop_x = set()
            if self.property_constraint:
                needs_prop_x.add(self.property_constraint["node_type"])

            node_ids = []
            for i in range(num_nodes):
                n_type = f"N{random.randint(1, self.num_node_types)}"  # assining random node label(eg N1) to every node_id
                uid = f"node_{i}"

                props_dict={"id":uid}  # WILL contain node_id and its properties

                # Generate YYYY-MM-DD string
                if n_type in needs_date:
                    start_dt = date(2000, 1, 1)
                    end_dt = date(2023, 12, 31) # did all this instead of just random_date to have control over timeline ask interviewer which would be better
                    delta = end_dt - start_dt     #get a range of days
                    random_days = random.randint(0, delta.days)   # select random number of days from that range
                    random_date = start_dt + timedelta(days=random_days)  # add it into start date to achieve randomness
                    props_dict["date_val"] = random_date #neo4j automatically castes it to date

                if n_type in needs_prop_x:
                    limit = self.property_constraint["threshold"]
                    x_val = random.randint(limit + 1, 100) # Valid value
                    props_dict["x"] = x_val

                # Join properties with commas and create node
                session.run(f"CREATE (n:{n_type} $props)", props=props_dict)

                node_ids.append((uid, n_type))

            global_neighbors = {uid: set() for uid, _ in node_ids} # to check neighbours in O(1)

            print("connecting nodes via edges...")
            # Snapshot the node list so the outer loop order is stable
            outer_nodes = list(node_ids)
            for src_id, src_type in outer_nodes:

                max_degree_limit = random.randint(3, 10)  # mathematically keeps graph sparse enough for instantaneous generation
                exclusive_forbidden = set()
                exclusive_rule = None
                dependency_rule = None
                temporal_rule = None

                if src_type in self.neighborhood_rules:             # for every SOURCE_NODE we check the constraints
                    rule = self.neighborhood_rules[src_type]        # we applied on it in generate_rules
                    if rule["type"] == "max_degree":
                        max_degree_limit = rule["limit"]
                    elif rule["type"] == "exclusive":
                        exclusive_rule = rule
                    elif rule["type"] == "dependency":
                        dependency_rule = rule
                    elif rule["type"] == "temporal":
                        temporal_rule = rule

                connections_made = 0
                # Shuffle a COPY for the inner loop so there is randomness in every run
                inner_targets = list(node_ids)
                random.shuffle(inner_targets)

                for tgt_id, tgt_type in inner_targets:      # currently O(N^2), if large no of nodes, would prefer selecting only
                    if src_id == tgt_id: continue           # some trgt_nodes at random or with similar property types
                    if connections_made >= max_degree_limit: break
                    if tgt_type in exclusive_forbidden: continue

                    target_is_willing = True  #if trgt passes all test, its ready to be connected to source
                    if tgt_type in self.neighborhood_rules:
                        tgt_rule = self.neighborhood_rules[tgt_type]
                        if tgt_rule["type"] == "exclusive":
                            pair = tgt_rule["conflict_pair"]
                            if src_type in pair:
                                enemy = pair[1] if src_type == pair[0] else pair[0] # also need to check if source is a good
                                if enemy in global_neighbors[tgt_id]:               # match for target,using global neighbours
                                    target_is_willing = False

                    if not target_is_willing: continue

                    possible_rels = [r for (s, r, t) in self.allowed_patterns
                                     if s == src_type and t == tgt_type]

                    if possible_rels and random.random() < 0.2:  #after all checks were passed still put randomness
                        r_type = random.choice(possible_rels)

                        #  TEMPORAL CONSTRAINT LOGIC
                        if temporal_rule and tgt_type == temporal_rule["target"] and r_type == temporal_rule["rel_type"]:

                            # just compare a.date_val > b.date_val directly
                            session.run(f"""
                                MATCH (a:{src_type} {{id: '{src_id}'}})
                                MATCH (b:{tgt_type} {{id: '{tgt_id}'}})
                                WHERE a.date_val <= b.date_val
                                // Fix: Make A one day after B
                                SET a.date_val = b.date_val + duration('P1D')
                            """)

                            #  A1:active given to edge if temporal rule is present on tgt and src otherwise no A1
                            #  flagging for manual verification and for LLM to also know
                            session.run(f"""
                                MATCH (a:{src_type} {{id: '{src_id}'}})
                                MATCH (b:{tgt_type} {{id: '{tgt_id}'}})
                                MERGE (a)-[:{r_type} {{A1: 'active'}}]->(b)
                            """)
                        else:        # otherwise case of temporal
                            session.run(f"""
                                MATCH (a:{src_type} {{id: '{src_id}'}})
                                MATCH (b:{tgt_type} {{id: '{tgt_id}'}})
                                MERGE (a)-[:{r_type}]->(b)
                            """)

                        connections_made += 1
                        global_neighbors[src_id].add(tgt_type)
                        global_neighbors[tgt_id].add(src_type)

                        #once nodes edges are added, we need to update the rules we defined in starting of this nested src and tgt loop  for further iterations
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

    #  INJECT 2-4 OF EACH VIOLATION TYPE
    def inject_violations(self):
        print("Injecting 2-4 of every possible violation type...")

        violation_types = ["triple", "cardinality", "exclusive", "dependency", "temporal", "property_x"]

        with self.driver.session() as session:
            total_success = 0

            with open("inconsistencies.txt", "w") as file: # writes in inconsistencies.txt for the model to see
                for v_type in violation_types:
                    num_to_inject = random.randint(20, 30)
                    inconsistency_query = ""
                    injected_this_type = 0

                    #  Lock the pattern BEFORE the loop so all iterations target the same type

                    # Triple: pick one disallowed pattern for all iterations
                    triple_src, triple_r, triple_tgt = (None, None, None)
                    if v_type == "triple" and self.disallowed_patterns:
                        triple_src, triple_r, triple_tgt = random.choice(list(self.disallowed_patterns))
                        inconsistency_query = f"MATCH (n1:{triple_src})-[r:{triple_r}]->(n2:{triple_tgt}) RETURN n1, r, n2"

                    # Cardinality: pick one max_degree node for all iterations
                    card_node, card_rule = (None, None)
                    if v_type == "cardinality":
                        cands = [k for k, v in self.neighborhood_rules.items() if v["type"] == "max_degree"]
                        if cands:
                            card_node = random.choice(cands)
                            card_rule = self.neighborhood_rules[card_node]
                            inconsistency_query = f"MATCH (n1:{card_node})-[r:{card_rule['rel_type']}]->(n2) WITH n1, count(r) AS deg WHERE deg > {card_rule['limit']} RETURN n1"

                    # Exclusive: pick one exclusive node type for all iterations
                    excl_node, excl_rule, excl_p1, excl_p2 = (None, None, None, None)
                    if v_type == "exclusive":
                        cands = [k for k, v in self.neighborhood_rules.items() if v["type"] == "exclusive"]
                        if cands:
                            excl_node = random.choice(cands)
                            excl_rule = self.neighborhood_rules[excl_node]
                            excl_p1, excl_p2 = excl_rule["conflict_pair"]
                            inconsistency_query = f"MATCH (n1:{excl_node})-[r1:{excl_rule['rel_type']}]->(n2:{excl_p1}), (n1)-[r2:{excl_rule['rel_type']}]->(n3:{excl_p2}) RETURN n1, r1, n2, r2, n3"

                    # Dependency: pick one dependency node type for all iterations
                    dep_node, dep_rule = (None, None)
                    if v_type == "dependency":
                        cands = [k for k, v in self.neighborhood_rules.items() if v["type"] == "dependency"]
                        if cands:
                            dep_node = random.choice(cands)
                            dep_rule = self.neighborhood_rules[dep_node]
                            inconsistency_query = (
                                f"MATCH (n1:{dep_node})-[r:{dep_rule['rel_type']}]->(n2:{dep_rule['trigger']}) "
                                f"WHERE NOT (n1)-[:{dep_rule['rel_type']}]->(:{dep_rule['required']}) RETURN n1, r, n2"
                            )

                    for _ in range(num_to_inject):
                        result = None

                        if v_type == "triple" and triple_src:
                            result = session.run(f"""
                                MATCH (a:{triple_src}), (b:{triple_tgt}) WHERE a.id <> b.id
                                WITH a, b ORDER BY rand() LIMIT 1
                                MERGE (a)-[:{triple_r}]->(b) RETURN a
                            """)

                        elif v_type == "cardinality" and card_node:
                            overflow = card_rule["limit"] + 2
                            result = session.run(f"""
                                MATCH (a:{card_node}) WITH a ORDER BY rand() LIMIT 1
                                MATCH (b) WHERE a <> b
                                WITH a, collect(b)[0..{overflow}] AS chosen UNWIND chosen AS b
                                MERGE (a)-[:{card_rule['rel_type']}]->(b) RETURN a
                            """)

                        elif v_type == "exclusive" and excl_node:
                            # Skip nodes already violated (both conflict types already connected)
                            result = session.run(f"""
                                MATCH (a:{excl_node})
                                WHERE NOT ((a)-[:{excl_rule['rel_type']}]->(:{excl_p1}) AND (a)-[:{excl_rule['rel_type']}]->(:{excl_p2}))
                                WITH a ORDER BY rand() LIMIT 1
                                MATCH (t1:{excl_p1}), (t2:{excl_p2}) WITH a, t1, t2 ORDER BY rand() LIMIT 1
                                MERGE (a)-[:{excl_rule['rel_type']}]->(t1)
                                MERGE (a)-[:{excl_rule['rel_type']}]->(t2) RETURN a
                            """)

                        elif v_type == "dependency" and dep_node:
                            # Only pick source nodes not already in violation state
                            merge_result = session.run(f"""
                                MATCH (a:{dep_node})
                                WHERE NOT (a)-[:{dep_rule['rel_type']}]->(:{dep_rule['trigger']})
                                   OR (a)-[:{dep_rule['rel_type']}]->(:{dep_rule['required']})
                                WITH a ORDER BY rand() LIMIT 1
                                MATCH (b:{dep_rule['trigger']}) WHERE b.id <> a.id
                                WITH a, b ORDER BY rand() LIMIT 1
                                MERGE (a)-[:{dep_rule['rel_type']}]->(b)
                                RETURN a.id AS src_id
                            """)
                            record = merge_result.single()
                            if record:
                                src_id = record["src_id"]
                                session.run(f"""
                                    MATCH (a:{dep_node} {{id: '{src_id}'}})-[r]->(c:{dep_rule['required']})
                                    DELETE r
                                """)
                                result = session.run(f"""
                                    MATCH (a:{dep_node} {{id: '{src_id}'}}) RETURN a
                                """)

                        elif v_type == "temporal":
                            temp_rule_node = None
                            temp_rule = None
                            for nt, rule in self.neighborhood_rules.items():
                                if rule["type"] == "temporal":
                                    temp_rule_node = nt
                                    temp_rule = rule
                                    break

                            if temp_rule:
                                # Ensure a valid temporal edge exists to corrupt
                                session.run(f"""
                                    MATCH (a:{temp_rule_node}), (b:{temp_rule['target']})
                                    WHERE a.id <> b.id AND a.date_val IS NOT NULL AND b.date_val IS NOT NULL
                                    WITH a, b ORDER BY rand() LIMIT 1
                                    MERGE (a)-[:{temp_rule['rel_type']} {{A1: 'active'}}]->(b)
                                    SET a.date_val = b.date_val + duration('P1D')
                                """)
                                # Corrupt a currently-valid temporal edge
                                result = session.run(f"""
                                    MATCH (a)-[r {{A1: 'active'}}]->(b)
                                    WHERE a.date_val > b.date_val
                                    WITH a, b ORDER BY rand() LIMIT 1
                                    SET a.date_val = b.date_val - duration('P10D')
                                    RETURN a
                                """)
                            inconsistency_query = f"MATCH (a)-[r {{A1: 'active'}}]->(b) WHERE a.date_val <= b.date_val RETURN a, r, b"

                        elif v_type == "property_x" and self.property_constraint:
                            target_type = self.property_constraint["node_type"]
                            threshold = self.property_constraint["threshold"]
                            # Each run picks the next eligible node (previously set nodes no longer match WHERE)
                            result = session.run(f"""
                                MATCH (n:{target_type}) WHERE n.x > {threshold}
                                WITH n LIMIT 1
                                SET n.x = {threshold} - 10
                                RETURN n
                            """)
                            inconsistency_query = f"MATCH (n:{target_type}) WHERE n.x <= {threshold} RETURN n"

                        if result and result.peek():
                            injected_this_type += 1

                    if injected_this_type > 0:
                        print(f"  [Success] Injected {injected_this_type} {v_type} violation(s).")
                        file.write(f"{inconsistency_query}\n")
                        total_success += injected_this_type
                    else:
                        print(f"  [Failed] Could not inject {v_type} violation (graph preconditions not met).")

            print(f"Finished. Total violations injected: {total_success}")

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
    gen = Generator("neo4j+s://83c28575.databases.neo4j.io", ("83c28575","KdSxwk54vkvXqx27YkwYIcobgPt6IDi3UE08K-eKMWU"))
    gen.clear_database()
    gen.generate_rules(num_allowed=250, num_disallowed=50)
    gen.generate_valid_graph(num_nodes=10000)
    gen.inject_violations()
    gen.export_ontology()
    gen.close()
