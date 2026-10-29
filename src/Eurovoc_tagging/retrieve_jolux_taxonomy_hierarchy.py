import json
from pathlib import Path
from rdflib import Graph
from SPARQLWrapper import SPARQLWrapper, JSON

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEDLEX_DATA_DIR = PROJECT_ROOT / "data" / "Fedlex"

CURRENT_FOLDER = Path(__file__).resolve().parents[0]

BASE_FEDLEX_TTL = FEDLEX_DATA_DIR / "rdf" / "fedlex_base_data.ttl"

ENDPOINT = "https://fedlex.data.admin.ch/sparqlendpoint"

g = Graph()
g.parse(BASE_FEDLEX_TTL, format="turtle")
print("loaded", len(g), "triples")

all_results = []

# Retrieve all base laws and taxonomy entries
query = """
PREFIX rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>

SELECT ?work
       (SAMPLE(?act_title) AS ?title)
       (GROUP_CONCAT(DISTINCT STR(?taxo); SEPARATOR=" || ") AS ?taxonomy)
WHERE {
    ?work rdf:type jolux:ConsolidationAbstract ;
          jolux:classifiedByTaxonomyEntry ?taxo ;
          jolux:isRealizedBy ?expr .
    ?expr jolux:language <http://publications.europa.eu/resource/authority/language/FRA> ;
          jolux:title ?act_title .
}
GROUP BY ?work
"""

for row in g.query(query):

    query_taxonomy = f"""

    PREFIX skos:<http://www.w3.org/2004/02/skos/core#>

    SELECT ?ancestor ?label (COUNT(DISTINCT ?x) AS ?level)
    WHERE {{
        BIND(<{row.taxonomy}> AS ?concept)

        ?ancestor skos:narrower* ?concept .     
        ?x skos:narrower* ?ancestor .          

        ?ancestor skos:prefLabel ?label .
        FILTER(lang(?label) = "fr")
    }}
    GROUP BY ?ancestor ?label
    ORDER BY ?level
    """

    s = SPARQLWrapper(ENDPOINT)
    s.setQuery(query_taxonomy)
    s.setReturnFormat(JSON)
    results = s.query().convert()
    rows = results["results"]["bindings"]

    all_results.append({
            "law_title": row.title,
            "taxonomy_entry": row.taxonomy,
            "hierarchy": [
                {"level": r["level"]["value"], "label": r["label"]["value"]}
                for r in rows
            ],
        })

with open(f"{CURRENT_FOLDER}/jolux_laws_concepts.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=2, ensure_ascii=False)

print("saved", len(all_results), "entries")