import requests
import json
from pathlib import Path
from rdflib import Graph
from SPARQLWrapper import SPARQLWrapper, JSON

def get_fedlex_resources(resource_uri):

    '''
    For each individual Fedlex resources (Acts, Consolidation, etc.) this function
    sends a GET request to the Fedlex server in order to retrieve the content of 
    the desired document in a TTL format

    '''

    ontology_path = "fedlex_base_data.ttl"

    headers = {
        "Accept": "text/turtle"
    }

    response = requests.get(resource_uri, headers=headers)
    response.raise_for_status()

    g = Graph()
    if Path(ontology_path).exists():
        g.parse(ontology_path, format="turtle")
    before = len(g)

    g.parse(data=response.text, format="turtle")
    g.serialize(ontology_path, format="turtle")

    print(f"Triples added for {resource_uri} : {len(g) - before}")



def get_fedlex_cosnolidations():

    '''
    Consolidations do not appear automatically when calling the GET request
    on the base legislations. In this regard, we use the Fedlex SPARQL endpoint
    to map all the retrieve laws to their consolidations

    '''

    ENDPOINT = "https://fedlex.data.admin.ch/sparqlendpoint"

    with open("fedlex_laws.json", encoding="utf-8") as f:
        laws = json.load(f)

    base_uris = [law["cc"] for law in laws.values() if law["cc"]]
    values = " ".join(f"<{uri}>" for uri in base_uris)

    query = f"""
    PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
    SELECT ?base ?consolidation WHERE {{
        VALUES ?base {{ {values} }}
        ?consolidation jolux:isMemberOf ?base .
    }}
    ORDER BY ?base ?consolidation
    """

    s = SPARQLWrapper(ENDPOINT)
    s.setQuery(query)
    s.setReturnFormat(JSON)
    rows = s.query().convert()["results"]["bindings"]

    consolidations = {uri: [] for uri in base_uris}
    for r in rows:
        consolidations[r["base"]["value"]].append(r["consolidation"]["value"])

    with open("fedlex_consolidations.json", "w", encoding="utf-8") as f:
        json.dump(consolidations, f, indent=2)

    for base, items in consolidations.items():
        print(f"{base}: {len(items)} consolidations")



# Load laws 
with open("fedlex_laws.json", encoding="utf-8") as f:
    laws = json.load(f)

for key, law in laws.items():
    for uri in (law["cc"], law["oc"]):
        if not uri:
            continue
        try:
            get_fedlex_resources(uri)
        except requests.HTTPError as e:
            print(f"Skipped {key} ({uri}): {e}")



# Enrich with consolidations
with open("fedlex_consolidations.json", encoding="utf-8") as f:
    consolidations = json.load(f)

for base, items in consolidations.items():
    for uri in items:
        get_fedlex_resources(uri)