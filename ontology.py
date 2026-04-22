import random
import json
import config

class OntologyGenerator:
    def __init__(self):
        self.num_node_types = config.NUM_NODE_TYPES
        self.num_rel_types = config.NUM_REL_TYPES
        
        self.allowed_patterns = set()
        self.disallowed_patterns = set()
        self.neighborhood_rules = {} 
        self.property_constraint = None

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
        
        # single node property check with random threshold
        active_types = set()
        for (s, r, t) in self.allowed_patterns:
            active_types.add(s)
            active_types.add(t)
        
        if active_types:
            target_type = random.choice(list(active_types))
            threshold_val = random.randint(*config.PROPERTY_THRESHOLD_RANGE)
            self.property_constraint = {
                "node_type": target_type,
                "threshold": threshold_val
            }

        # Neighborhood Constraints
        for n_type in all_node_types:
            rand_val = random.random()
            
            # Max Degree
            if rand_val < config.PROB_MAX_DEGREE:
                self.neighborhood_rules[n_type] = {
                    "type": "max_degree",
                    "limit": random.randint(*config.MAX_DEGREE_LIMIT_RANGE),
                    "rel_type": random.choice(all_rel_types)
                }
            
            # Exclusive
            elif rand_val < config.PROB_EXCLUSIVE:
                others = [t for t in all_node_types if t != n_type]
                if len(others) >= 2:
                    self.neighborhood_rules[n_type] = {
                        "type": "exclusive",
                        "conflict_pair": random.sample(others, 2), 
                        "rel_type": random.choice(all_rel_types)
                    }

            # Dependency
            elif rand_val < config.PROB_DEPENDENCY:
                others = [t for t in all_node_types if t != n_type]  
                if len(others) >= 2:
                    pair = random.sample(others, 2)
                    self.neighborhood_rules[n_type] = {
                        "type": "dependency",
                        "trigger": pair[0],   
                        "required": pair[1],  
                        "rel_type": random.choice(all_rel_types)
                    }
            
            # Temporal Rule
            else:
                others = [t for t in all_node_types if t != n_type]
                if others:
                    target = random.choice(others)
                    self.neighborhood_rules[n_type] = {
                        "type": "temporal",
                        "target": target,
                        "rel_type": random.choice(all_rel_types) 
                    }

        # Guarantee Blocks
        self._ensure_rule("temporal", all_node_types, all_rel_types)
        self._ensure_rule("dependency", all_node_types, all_rel_types)
        self._ensure_rule("max_degree", all_node_types, all_rel_types)
        self._ensure_rule("exclusive", all_node_types, all_rel_types)

    def _ensure_rule(self, rule_type, all_node_types, all_rel_types):
        if not any(v["type"] == rule_type for v in self.neighborhood_rules.values()):
            unassigned = [t for t in all_node_types if t not in self.neighborhood_rules]
            fallback_type = random.choice(unassigned if unassigned else all_node_types)
            others = [t for t in all_node_types if t != fallback_type]
            
            if rule_type == "temporal":
                self.neighborhood_rules[fallback_type] = {
                    "type": "temporal",
                    "target": random.choice(others),
                    "rel_type": random.choice(all_rel_types)
                }
            elif rule_type == "dependency":
                pair = random.sample(others, 2)
                self.neighborhood_rules[fallback_type] = {
                    "type": "dependency",
                    "trigger": pair[0],
                    "required": pair[1],
                    "rel_type": random.choice(all_rel_types)
                }
            elif rule_type == "max_degree":
                self.neighborhood_rules[fallback_type] = {
                    "type": "max_degree",
                    "limit": random.randint(*config.MAX_DEGREE_LIMIT_RANGE),
                    "rel_type": random.choice(all_rel_types)
                }
            elif rule_type == "exclusive":
                self.neighborhood_rules[fallback_type] = {
                    "type": "exclusive",
                    "conflict_pair": random.sample(others, 2),
                    "rel_type": random.choice(all_rel_types)
                }
            print(f"  [Guaranteed] Assigned {rule_type} rule to {fallback_type}")

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
