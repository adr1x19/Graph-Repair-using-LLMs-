# Neo4j Configuration
NEO4J_URI = "neo4j+s://3d49ba2d.databases.neo4j.io"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = "swLRHNP8hZEyF8bSnFBJqZBuKXel2v4ZgqBgA_5a4Dg"
NEO4J_DATABASE = "neo4j"

# Aura Configuration
AURA_INSTANCEID = "3d49ba2d"
AURA_INSTANCENAME = "Instance01"

# Ollama Configuration
OLLAMA_HOST = "https://ollama.com"
OLLAMA_AUTH_HEADER = {'Authorization': 'Bearer 5c223e289b3a44dab9d3e35f2daf61f5.R3XOvVQZAAsKeSQaE4Gfxbd4'}
OLLAMA_MODEL = 'qwen3.5:cloud'

# Map URI to URL variable name used in logic
NEO4J_URL = NEO4J_URI

# --- Ontology & Graph Generation Configuration ---
NUM_NODE_TYPES = 50
NUM_REL_TYPES = 15
NUM_NODES = 80 # Adjust up to 10000 for scaling runs

# Generation probabilities for constraints
PROB_MAX_DEGREE = 0.2
PROB_EXCLUSIVE = 0.5    # Threshold (0.2 to 0.5 -> 30%)
PROB_DEPENDENCY = 0.75  # Threshold (0.5 to 0.75 -> 25%)
# Remaining probability implicitly comparison (0.75 to 1.0 -> 25%)

# Generation settings
MAX_DEGREE_LIMIT_RANGE = (1, 5)
PROPERTY_THRESHOLD_RANGE = (30, 70)
RELATION_CREATION_PROBABILITY = 0.2
INJECTION_COUNT_RANGE = (20, 30)

# Comparison property (prop) range
PROP_MIN_VAL = 0
PROP_MAX_VAL = 1000

# --- Property & Violation Offsets ---
PROPERTY_MAX_VALUE = 100
PROPERTY_VIOLATION_OFFSET = 10 

# Cardinality overflow offset
CARDINALITY_OVERFLOW_OFFSET = 2

# Comparison logic (N1.prop > N2.prop)
COMPARISON_INCREMENT = 5 #The "safety buffer" used to make a node valid if it's currently failing the rule.
COMPARISON_VIOLATION_OFFSET = 20 #he amount subtracted to intentionally break the rule during violation injection.

# Overlap specific
NUM_HUBS = 3