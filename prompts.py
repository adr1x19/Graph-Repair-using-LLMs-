DESCRIBE_QUERY_PROMPT = """
{database_description}
Describe this query:{query} in detail,make a short paragraph.
Return only the paragraph.
"""

GENERATE_REPAIRS_PROMPT = """
{database_description}
The database has inconsistencies that we want to remove.
One such inconsistency is{formatted_inconsistency}.
Try to generate a query that removes the inconsistency.
IMP:When generating the query also remember to use the description to retrieve the pattern then remove the inconsisteny.
Return the best cypher query fix you can think of.
Make sure it is in proper format with a semi-colon denoting the end.
(Generate the cypher queries only.)
"""
