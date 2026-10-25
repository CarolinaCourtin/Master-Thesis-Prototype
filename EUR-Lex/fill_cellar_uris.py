import json
from SPARQLWrapper import SPARQLWrapper, JSON

ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"
laws_file = "eurlex_laws.json"

with open(laws_file, encoding="utf-8") as f:
    laws = json.load(f)

for key, law in laws.items():
    # Find the act through its CELEX number, and read back the ELI stored in Cellar
    query = f"""
    PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
    SELECT DISTINCT ?work ?eli WHERE {{
        ?work cdm:resource_legal_id_celex ?celex .
        FILTER(STR(?celex) = "{law['celex']}")
        OPTIONAL {{ ?work cdm:resource_legal_eli ?eli }}
        FILTER(STRSTARTS(STR(?work), "http://publications.europa.eu/resource/cellar/"))
    }}
    """
    sparql = SPARQLWrapper(ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()["results"]["bindings"]

    if not results:
        print(f"{key}: CELEX {law['celex']} not found")
        continue

    law["cellar"] = results[0]["work"]["value"]

    # Check the ELI written in the JSON against the one Cellar has
    cellar_eli = results[0].get("eli", {}).get("value")
    if cellar_eli and cellar_eli != law["eli"]:
        print(f"{key}: ELI corrected {law['eli']} -> {cellar_eli}")
        law["eli"] = cellar_eli

    print(f"{key}: {law['cellar']}")

with open(laws_file, "w", encoding="utf-8") as f:
    json.dump(laws, f, indent=2, ensure_ascii=False)

missing = [k for k, l in laws.items() if not l["cellar"]]
print(f"\nDone. {len(laws) - len(missing)}/{len(laws)} cellar URIs filled. Missing: {missing or 'none'}")
