import json
from pathlib import Path
from rdflib import Graph
from SPARQLWrapper import SPARQLWrapper, JSON
from rdflib import Graph, URIRef, Namespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEDLEX_DATA_DIR = PROJECT_ROOT / "data" / "Fedlex"
EURLEX_DATA_DIR = PROJECT_ROOT / "data" / "EUR_Lex"
CURRENT_FOLDER = Path(__file__).resolve().parents[0]

FEDLEX_LAWS = FEDLEX_DATA_DIR / "raw" / "fedlex_laws.json"
EURLEX_LAWS = EURLEX_DATA_DIR / "raw" / "eurlex_laws.json"

EURLEX_CONCEPTS = CURRENT_FOLDER / "eurlex_laws_concepts.json"

BASE_FEDLEX_TTL = FEDLEX_DATA_DIR / "rdf" / "fedlex_base_data.ttl"
ENRICHED_FEDLEX_TTL = FEDLEX_DATA_DIR / "rdf" / "fedlex_data_enriched_eurovoc.ttl"


ELI = Namespace("http://data.europa.eu/eli/ontology#")


with open(EURLEX_LAWS, encoding="utf-8") as f:
    eurlex_laws = json.load(f)

with open(FEDLEX_LAWS, encoding="utf-8") as f2:
    fedlex_laws = json.load(f2)

with open(EURLEX_CONCEPTS, encoding="utf-8") as f3:
    eurlex_concepts = json.load(f3)

g = Graph()
g.parse(BASE_FEDLEX_TTL, format="turtle")
triples_before = len(g)

concepts_by_law = {}
for item in eurlex_concepts:
    concepts_by_law[item["uri"]] = item.get("concepts", [])


for key, law in eurlex_laws.items():
    cellar = law.get("cellar")
    swiss_eq = law.get("swiss_equivalent", [])

    concepts = concepts_by_law.get(cellar) # concepts of this specific law
    if concepts is None:
        print(f"{key} : no concepts found for {cellar}")
        continue


    # remove eurovoc concepts of domain 10 (EUROPEAN UNION)
    concepts_to_add = []
    for concept in concepts:
        domain = ""
        for level in concept.get("hierarchy", []):
            if level.get("level") == 1:
                domain = level.get("label", "")

        if domain.startswith("10 "):
            continue                           # domaine 10 : on passe au concept suivant

        concepts_to_add.append(concept["uri"])  # uniquement l'URI du concept lui-même


    for swiss_key in swiss_eq:
        swiss_law = fedlex_laws.get(swiss_key)
        if not swiss_law:
            print(f"  {swiss_key} not in fedlex_laws.json")
            continue

        if swiss_law.get("cc"):
            print(f"EUROVOC concepts added for swiss law : {swiss_law.get('cc')}")
            for concept_uri in concepts_to_add:
                g.add((URIRef(swiss_law.get('cc')), ELI.is_about, URIRef(concept_uri)))
                print(f"\n {concept_uri}")

        if swiss_law.get("oc"):
            print(f"EUROVOC concepts added for swiss law : {swiss_law.get('oc')}")
            for concept_uri in concepts_to_add:
                g.add((URIRef(swiss_law.get('oc')), ELI.is_about, URIRef(concept_uri)))
                print(f"\n {concept_uri}")

        if swiss_law.get("fga"):
            print(f"EUROVOC concepts added for swiss law : {swiss_law.get('fga')}")
            for concept_uri in concepts_to_add:
                g.add((URIRef(swiss_law.get('fga')), ELI.is_about, URIRef(concept_uri)))
                print(f"\n {concept_uri}")
        

g.serialize(ENRICHED_FEDLEX_TTL, format="turtle")
print(f"{len(g) - triples_before} new triples added")