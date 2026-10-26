import json
from pathlib import Path
import requests
from rdflib import Graph
from SPARQLWrapper import SPARQLWrapper, JSON

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEDLEX_DATA_DIR = PROJECT_ROOT / "data" / "Fedlex"
FEDLEX_DATA_DIR.mkdir(parents=True, exist_ok=True)

LAWS_JSON = FEDLEX_DATA_DIR / "raw" / "fedlex_laws.json"
CONSOLIDATIONS_JSON = FEDLEX_DATA_DIR / "raw" / "fedlex_consolidations.json"
BASE_FEDLEX_TTL = FEDLEX_DATA_DIR / "rdf" / "fedlex_base_data.ttl"

ENDPOINT = "https://fedlex.data.admin.ch/sparqlendpoint"


def get_fedlex_resources(resource_uri):

    
    #  For each individual Fedlex resource (Acts, Consolidations, etc.) this function
    #  sends a GET request to the Fedlex server to retrieve the document in Turtle,
    #  and adds it to the base legal resources TTL file.


    response = requests.get(resource_uri, headers={"Accept": "text/turtle"})
    response.raise_for_status()

    g = Graph()
    if BASE_FEDLEX_TTL.exists():
        g.parse(BASE_FEDLEX_TTL, format="turtle")
    before = len(g)

    g.parse(data=response.text, format="turtle")
    g.serialize(BASE_FEDLEX_TTL, format="turtle")

    print(f"Triples added for {resource_uri} : {len(g) - before}")



def get_fedlex_consolidations():


    #  Consolidations do not appear automatically when calling the GET request
    #  on the base legislations. We use the Fedlex SPARQL endpoint to map all
    #  the retrieved laws to their consolidations. This function finds the 
    #  set of consolidations linked to an law, and saves them in the CONSOLIDATIONS_JSON file.
    

    with open(LAWS_JSON, encoding="utf-8") as f:
        laws = json.load(f)

    cc_uris = []
    for law in laws.values():
        if law["cc"]:
            cc_uris.append(law["cc"])

    consolidations = {}

    for uri in cc_uris:
        query = f"""
        PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
        SELECT ?consolidation WHERE {{
            ?consolidation jolux:isMemberOf <{uri}> .
        }}
        ORDER BY ?consolidation
        """

        s = SPARQLWrapper(ENDPOINT)
        s.setQuery(query)
        s.setReturnFormat(JSON)
        results = s.query().convert()
        rows = results["results"]["bindings"]

        consolidations[uri] = []
        for row in rows:
            consolidations[uri].append(row["consolidation"]["value"])

    with open(CONSOLIDATIONS_JSON, "w", encoding="utf-8") as f:
        json.dump(consolidations, f, indent=2)

    for base_law, items in consolidations.items():
        print(f"{base_law} : {len(items)} consolidations")


# Load laws
with open(LAWS_JSON, encoding="utf-8") as f:
    laws = json.load(f)

for key, law in laws.items():

    uris_to_fetch = [law["cc"], law["oc"]]

    for uri in uris_to_fetch:
        if not uri:
            continue
        try:
            get_fedlex_resources(uri)
        except requests.HTTPError as e:
            print(f"Skipped {key} ({uri}) : {e}")


# Load consolidations
get_fedlex_consolidations()


# Retrieve the consolidations respective metadata and dump them in the TTL database 
with open(CONSOLIDATIONS_JSON, encoding="utf-8") as f:
    consolidations = json.load(f)

for base, items in consolidations.items():
    for uri in items:
        get_fedlex_resources(uri)