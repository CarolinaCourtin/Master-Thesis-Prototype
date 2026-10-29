import json
from pathlib import Path
from rdflib import Graph
from SPARQLWrapper import SPARQLWrapper, JSON

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EURLEX_DATA_DIR = PROJECT_ROOT / "data" / "EUR_Lex"
EUROVOC = PROJECT_ROOT / "data" / "Eurovoc" / "eurovoc-skos-ap-act.rdf"   

CURRENT_FOLDER = Path(__file__).resolve().parents[0]
BASE_EURLEX_TTL = EURLEX_DATA_DIR / "rdf" / "eurlex_base_data.ttl"

g_eurlex = Graph()
g_eurlex.parse(BASE_EURLEX_TTL, format="turtle")

'''
g_eurovoc = Graph()
g_eurovoc.parse(EUROVOC, format="xml")
''' # loading the query in GraphDB for large files

graphdb = SPARQLWrapper("http://localhost:7200/repositories/Digital_Law_Harmonization")
graphdb.setReturnFormat(JSON)


query1 = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>

SELECT ?work (SAMPLE(?act_title) AS ?title)
       (GROUP_CONCAT(DISTINCT STR(?eurovoc_concept); SEPARATOR=" || ") AS ?concepts)
WHERE {
    ?work cdm:work_is_about_concept_eurovoc ?eurovoc_concept .
    ?expression cdm:expression_belongs_to_work ?work ;
                cdm:expression_title ?act_title ;
                cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/FRA> .
}
GROUP BY ?work
"""

all_results = []

for row in g_eurlex.query(query1):                        

    law = {
        "law_title": str(row.title),
        "concepts": [],                                   
    }
    concept_uris = str(row.concepts).split(" || ")

    for concept in concept_uris:                           # one concept of this law


        query2 = f"""
        PREFIX skos:  <http://www.w3.org/2004/02/skos/core#>
        PREFIX euvoc: <http://publications.europa.eu/ontology/euvoc#>

        SELECT ?ancestor ?label (COUNT(DISTINCT ?x) AS ?level)
        FROM <http://example.org/graph/eurovoc>
        WHERE {{
            BIND(<{concept}> AS ?concept)

            ?concept (skos:broader|skos:topConceptOf|euvoc:domain)* ?ancestor .
            ?ancestor (skos:broader|skos:topConceptOf|euvoc:domain)* ?x .

            FILTER(?x NOT IN (<http://eurovoc.europa.eu/100141>, <http://eurovoc.europa.eu/domains>))

            ?ancestor skos:prefLabel ?label .
            FILTER(lang(?label) = "fr")
        }}
        GROUP BY ?ancestor ?label
        ORDER BY ?level
        """

        graphdb.setQuery(query2)
        rows = graphdb.query().convert()["results"]["bindings"]

        hierarchy = []
        for r in rows:
            hierarchy.append({"level": int(r["level"]["value"]), "label": r["label"]["value"]})

        law["concepts"].append({
            "uri": concept,
            "label": hierarchy[-1]["label"] if hierarchy else None,   # last row = the concept itself
            "hierarchy": hierarchy,
        })

    all_results.append(law)                                # one entry per law

with open(CURRENT_FOLDER / "eurlex_laws_concepts.json", "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=2, ensure_ascii=False)

print("saved", len(all_results), "laws")