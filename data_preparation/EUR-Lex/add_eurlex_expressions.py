import json
import time
from rdflib import Graph, URIRef, Literal, BNode
from SPARQLWrapper import SPARQLWrapper, JSON

ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"
PAGE_SIZE = 5000
LANGUAGE_URI = "http://publications.europa.eu/resource/authority/language/{}"


def to_rdf(value):
    """Convert one value from the SPARQL JSON result into an rdflib term."""
    if value["type"] == "uri":
        return URIRef(value["value"])
    if value["type"] == "bnode":
        return BNode(value["value"])
    return Literal(value["value"], lang=value.get("xml:lang"), datatype=value.get("datatype"))


def run_paged(query):
    """Run a SELECT ?s ?p ?o query page by page and return all the rows."""
    rows, offset = [], 0
    while True:
        sparql = SPARQLWrapper(ENDPOINT)
        sparql.setQuery(f"{query} ORDER BY ?s ?p ?o LIMIT {PAGE_SIZE} OFFSET {offset}")
        sparql.setReturnFormat(JSON)
        sparql.setTimeout(300)
        page = sparql.query().convert()["results"]["bindings"]
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE
        time.sleep(1)


def add_expressions_manifestations_items(laws_file="eurlex_laws.json",
                                         ttl_file="eurlex_base_data.ttl",
                                         language=None):
    """
    For each law, runs three queries (expressions, manifestations, items) and adds
    all the triples of these resources to the existing TTL file.

    language: None for every language, or a 3-letter EU code such as "FRA".
    """
    with open(laws_file, encoding="utf-8") as f:
        laws = json.load(f)

    g = Graph()
    g.parse(ttl_file, format="turtle")
    triples_before = len(g)

    language_filter = ""
    if language:
        language_filter = f"?expr cdm:expression_uses_language <{LANGUAGE_URI.format(language)}> ."

    for key, law in laws.items():
        cellar = law.get("cellar")
        if not cellar:
            print(f"{key}: no cellar URI, skipped")
            continue

        queries = {
            # 1. Expressions of the law
            "expressions": f"""
                PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
                SELECT ?s ?p ?o WHERE {{
                    ?s cdm:expression_belongs_to_work <{cellar}> .
                    {language_filter.replace("?expr", "?s")}
                    ?s ?p ?o .
                }}""",

            # 2. Manifestations of these expressions
            "manifestations": f"""
                PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
                SELECT ?s ?p ?o WHERE {{
                    ?expr cdm:expression_belongs_to_work <{cellar}> .
                    {language_filter}
                    ?s cdm:manifestation_manifests_expression ?expr .
                    ?s ?p ?o .
                }}""",

            # 3. Items of these manifestations
            "items": f"""
                PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
                SELECT ?s ?p ?o WHERE {{
                    ?expr cdm:expression_belongs_to_work <{cellar}> .
                    {language_filter}
                    ?manif cdm:manifestation_manifests_expression ?expr .
                    ?s cdm:item_belongs_to_manifestation ?manif .
                    ?s ?p ?o .
                }}""",
        }

        counts = {}
        for level, query in queries.items():
            try:
                rows = run_paged(query)
            except Exception as e:
                print(f"{key} ({level}): query failed: {e}")
                counts[level] = "error"
                continue
            for r in rows:
                g.add((to_rdf(r["s"]), to_rdf(r["p"]), to_rdf(r["o"])))
            counts[level] = len(rows)

        print(f"{key}: {counts}")

    g.serialize(ttl_file, format="turtle")
    print(f"\nSaved {len(g)} triples to {ttl_file} ({len(g) - triples_before} new)")


add_expressions_manifestations_items()  # all languages; use language="FRA" for French only
