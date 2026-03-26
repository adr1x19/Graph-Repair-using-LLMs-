import neo4j
from neo4j import GraphDatabase
from typing import Any, Dict
from database import GraphDB
# driver 
URI="neo4j+s://9738bd7b.databases.neo4j.io"
AUTH=("neo4j","JMOdIBduJdKFNl560eV6CTVWlpYE0iklAstPv7DuDjs")

NODE_PROPERTIES_QUERY = """
CALL apoc.meta.data()
YIELD label, other, elementType, type, property
WHERE NOT type = "RELATIONSHIP" AND elementType = "node"
WITH label AS nodeLabels, collect({property:property, type:type}) AS properties
RETURN {labels: nodeLabels, properties: properties} AS output
"""
REL_PROPERTIES_QUERY = """
CALL apoc.meta.data()
YIELD label, other, elementType, type, property
WHERE NOT type = "RELATIONSHIP" AND elementType = "relationship"
WITH label AS relType, collect({property:property, type:type}) AS properties
RETURN {type: relType, properties: properties} AS output
"""
REL_QUERY = """
CALL apoc.meta.data()
YIELD label, other, elementType, type, property
WHERE type = "RELATIONSHIP" AND elementType = "node"
UNWIND other AS other_node
RETURN {start: label, type: property, end: toString(other_node)} AS output
"""



def get_structured_schema(driver:GraphDB) -> dict[str, Any]:
    node_labels_response = driver.run_query(NODE_PROPERTIES_QUERY)
    node_properties = [
        data["output"]
        for data in [r for r in node_labels_response]
    ]
    rel_properties_query_response = driver.run_query(REL_PROPERTIES_QUERY)
    rel_properties = [
        data["output"]
        for data in [r for r in rel_properties_query_response]
    ]
    rel_query_response = driver.run_query(REL_QUERY)
    relationships = [
        data["output"]
        for data in [r for r in rel_query_response]
    ]
    return {
        "node_props": {el["labels"]: el["properties"] for el in 
node_properties},
        "rel_props": {el["type"]: el["properties"] for el in rel_properties},
        "relationships": relationships,
    }

def get_schema(structured_schema: dict[str, Any]) -> str:
    def _format_props(props: list[dict[str, Any]]) -> str:
        return ", ".join([f"{prop['property']}: {prop['type']}" for prop in props])
    formatted_node_props = [
        f"{label} {{{_format_props(props)}}}"
        for label, props in structured_schema["node_props"].items()
    ]
    formatted_rel_props = [
        f"{rel_type} {{{_format_props(props)}}}"
        for rel_type, props in structured_schema["rel_props"].items()
    ]
    formatted_rels = [
        f"(:{element['start']})-[:{element['type']}]->(:{element['end']})"
        for element in structured_schema["relationships"]
    ]
    return "\n".join(
        [
            "Node labels and properties:",
            "\n".join(formatted_node_props),
            "Relationship types and properties:",
            "\n".join(formatted_rel_props),
            "The relationships:",
            "\n".join(formatted_rels),
        ]
    )


# with GraphDatabase.driver(URI, auth=AUTH) as driver:
#     try:
#         driver.verify_connectivity()
#         print("Connection successful!")
#     except Exception as e:
#         print(f"Connection failed: {e}")

#     output=get_structured_schema(driver)
#     schema=get_schema(output)
#     print(schema)
