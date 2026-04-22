import random
import config

class ViolationInjector:
    def __init__(self, db, ontology):
        self.db = db
        self.ontology = ontology

    def inject_violations(self):
        print("Injecting violations...")

        violation_types = ["triple", "cardinality", "exclusive", "dependency", "temporal", "property_x"]
        total_success = 0

        with open("inconsistencies.txt", "w") as file:
            for v_type in violation_types:
                num_to_inject = random.randint(*config.INJECTION_COUNT_RANGE)
                inconsistency_query = ""
                injected_this_type = 0

                triple_src, triple_r, triple_tgt = (None, None, None)
                if v_type == "triple" and self.ontology.disallowed_patterns:
                    triple_src, triple_r, triple_tgt = random.choice(list(self.ontology.disallowed_patterns))
                    inconsistency_query = f"MATCH (n1:{triple_src})-[r:{triple_r}]->(n2:{triple_tgt}) RETURN n1, r, n2"

                card_node, card_rule = (None, None)
                if v_type == "cardinality":
                    cands = [k for k, v in self.ontology.neighborhood_rules.items() if v["type"] == "max_degree"]
                    if cands:
                        card_node = random.choice(cands)
                        card_rule = self.ontology.neighborhood_rules[card_node]
                        inconsistency_query = f"MATCH (n1:{card_node})-[r:{card_rule['rel_type']}]->(n2) WITH n1, count(r) AS deg WHERE deg > {card_rule['limit']} RETURN n1"

                excl_node, excl_rule, excl_p1, excl_p2 = (None, None, None, None)
                if v_type == "exclusive":
                    cands = [k for k, v in self.ontology.neighborhood_rules.items() if v["type"] == "exclusive"]
                    if cands:
                        excl_node = random.choice(cands)
                        excl_rule = self.ontology.neighborhood_rules[excl_node]
                        excl_p1, excl_p2 = excl_rule["conflict_pair"]
                        inconsistency_query = f"MATCH (n1:{excl_node})-[r1:{excl_rule['rel_type']}]->(n2:{excl_p1}), (n1)-[r2:{excl_rule['rel_type']}]->(n3:{excl_p2}) RETURN n1, r1, n2, r2, n3"

                dep_node, dep_rule = (None, None)
                if v_type == "dependency":
                    cands = [k for k, v in self.ontology.neighborhood_rules.items() if v["type"] == "dependency"]
                    if cands:
                        dep_node = random.choice(cands)
                        dep_rule = self.ontology.neighborhood_rules[dep_node]
                        inconsistency_query = (
                            f"MATCH (n1:{dep_node})-[r:{dep_rule['rel_type']}]->(n2:{dep_rule['trigger']}) "
                            f"WHERE NOT (n1)-[:{dep_rule['rel_type']}]->(:{dep_rule['required']}) RETURN n1, r, n2"
                        )

                for _ in range(num_to_inject):
                    result = None

                    if v_type == "triple" and triple_src:
                        result = self.db.run_query(f"""
                            MATCH (a:{triple_src}), (b:{triple_tgt}) WHERE a.id <> b.id
                            WITH a, b ORDER BY rand() LIMIT 1
                            MERGE (a)-[:{triple_r}]->(b) RETURN a
                        """)

                    elif v_type == "cardinality" and card_node:
                        overflow = card_rule["limit"] + 2
                        result = self.db.run_query(f"""
                            MATCH (a:{card_node}) WITH a ORDER BY rand() LIMIT 1
                            MATCH (b) WHERE a <> b
                            WITH a, collect(b)[0..{overflow}] AS chosen UNWIND chosen AS b
                            MERGE (a)-[:{card_rule['rel_type']}]->(b) RETURN a
                        """)

                    elif v_type == "exclusive" and excl_node:
                        result = self.db.run_query(f"""
                            MATCH (a:{excl_node})
                            WHERE NOT ((a)-[:{excl_rule['rel_type']}]->(:{excl_p1}) AND (a)-[:{excl_rule['rel_type']}]->(:{excl_p2}))
                            WITH a ORDER BY rand() LIMIT 1
                            MATCH (t1:{excl_p1}), (t2:{excl_p2}) WITH a, t1, t2 ORDER BY rand() LIMIT 1
                            MERGE (a)-[:{excl_rule['rel_type']}]->(t1)
                            MERGE (a)-[:{excl_rule['rel_type']}]->(t2) RETURN a
                        """)

                    elif v_type == "dependency" and dep_node:
                        merge_result = self.db.run_query(f"""
                            MATCH (a:{dep_node})
                            WHERE NOT (a)-[:{dep_rule['rel_type']}]->(:{dep_rule['trigger']})
                               OR (a)-[:{dep_rule['rel_type']}]->(:{dep_rule['required']})
                            WITH a ORDER BY rand() LIMIT 1
                            MATCH (b:{dep_rule['trigger']}) WHERE b.id <> a.id
                            WITH a, b ORDER BY rand() LIMIT 1
                            MERGE (a)-[:{dep_rule['rel_type']}]->(b)
                            RETURN a.id AS src_id
                        """)
                        if merge_result:
                            src_id = merge_result[0]["src_id"]
                            self.db.run_query(f"""
                                MATCH (a:{dep_node} {{id: '{src_id}'}})-[r]->(c:{dep_rule['required']})
                                DELETE r
                            """)
                            result = self.db.run_query(f"""
                                MATCH (a:{dep_node} {{id: '{src_id}'}}) RETURN a
                            """)

                    elif v_type == "temporal":
                        temp_rule_node = None
                        temp_rule = None
                        for nt, rule in self.ontology.neighborhood_rules.items():
                            if rule["type"] == "temporal":
                                temp_rule_node = nt
                                temp_rule = rule
                                break

                        if temp_rule:
                            self.db.run_query(f"""
                                MATCH (a:{temp_rule_node}), (b:{temp_rule['target']})
                                WHERE a.id <> b.id AND a.date_val IS NOT NULL AND b.date_val IS NOT NULL
                                WITH a, b ORDER BY rand() LIMIT 1
                                MERGE (a)-[:{temp_rule['rel_type']} {{A1: 'active'}}]->(b)
                                SET a.date_val = b.date_val + duration('P1D')
                            """)
                            result = self.db.run_query(f"""
                                MATCH (a)-[r {{A1: 'active'}}]->(b)
                                WHERE a.date_val > b.date_val
                                WITH a, b ORDER BY rand() LIMIT 1
                                SET a.date_val = b.date_val - duration('P10D')
                                RETURN a
                            """)
                        inconsistency_query = f"MATCH (a)-[r {{A1: 'active'}}]->(b) WHERE a.date_val <= b.date_val RETURN a, r, b"

                    elif v_type == "property_x" and self.ontology.property_constraint:
                        target_type = self.ontology.property_constraint["node_type"]
                        threshold = self.ontology.property_constraint["threshold"]
                        result = self.db.run_query(f"""
                            MATCH (n:{target_type}) WHERE n.x > {threshold}
                            WITH n LIMIT 1
                            SET n.x = {threshold} - 10
                            RETURN n
                        """)
                        inconsistency_query = f"MATCH (n:{target_type}) WHERE n.x <= {threshold} RETURN n"

                    if result:
                        injected_this_type += 1

                if injected_this_type > 0:
                    print(f"  [Success] Injected {injected_this_type} {v_type} violation(s).")
                    file.write(f"{inconsistency_query}\n")
                    total_success += injected_this_type
                else:
                    print(f"  [Failed] Could not inject {v_type} violation (graph preconditions not met).")

        print(f"Finished. Total violations injected: {total_success}")
