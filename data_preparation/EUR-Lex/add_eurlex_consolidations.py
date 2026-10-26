import json
import time
from rdflib import Graph, URIRef, Literal, BNode, Namespace
from SPARQLWrapper import SPARQLWrapper, JSON

ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"
PAGE_SIZE = 5000
LANGUAGE_URI = "http://publications.europa.eu/resource/authority/language/{}"
CDM = Namespace("http://publications.europa.eu/ontology/cdm#")


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


def add_consolidations(laws_file="eurlex_laws.json",
                       ttl_file="eurlex_base_data.ttl",
                       language=None,
                       include_other_acts=False):
    """
    Adds the full data of the consolidated versions of each law to the TTL file:
    the consolidation's own metadata, its expressions, manifestations and items.

    language: None for every language, or a 3-letter EU code such as "FRA".
    include_other_acts: False keeps only the consolidations OF your laws
        (act_consolidated_based_on_resource_legal). True also adds consolidations
        of other acts that your laws amended (act_consolidated_consolidates_resource_legal).
    """
    with open(laws_file, encoding="utf-8") as f:
        laws = json.load(f)

    g = Graph()
    g.parse(ttl_file, format="turtle")
    triples_before = len(g)

    # Find the consolidations already linked to the laws in the TTL file
    consolidations = {}  # consolidation URI -> law key
    for key, law in laws.items():
        if not law.get("cellar"):
            continue
        law_uri = URIRef(law["cellar"])
        for c in g.subjects(CDM.act_consolidated_based_on_resource_legal, law_uri):
            consolidations[str(c)] = key
        if include_other_acts:
            for c in g.subjects(CDM.act_consolidated_consolidates_resource_legal, law_uri):
                consolidations.setdefault(str(c), key)

    print(f"{len(consolidations)} consolidations to fetch\n")

    language_filter = ""
    if language:
        language_filter = f"?expr cdm:expression_uses_language <{LANGUAGE_URI.format(language)}> ."

    log = {}
    for i, (cons, key) in enumerate(sorted(consolidations.items(), key=lambda x: x[1]), 1):
        queries = {
            # 1. The consolidation itself (its metadata)
            "metadata": f"""
                SELECT ?s ?p ?o WHERE {{
                    <{cons}> ?p ?o .
                    BIND(<{cons}> AS ?s)
                }}""",

            # 2. Its expressions
            "expressions": f"""
                PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
                SELECT ?s ?p ?o WHERE {{
                    ?s cdm:expression_belongs_to_work <{cons}> .
                    {language_filter.replace("?expr", "?s")}
                    ?s ?p ?o .
                }}""",

            # 3. Their manifestations
            "manifestations": f"""
                PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
                SELECT ?s ?p ?o WHERE {{
                    ?expr cdm:expression_belongs_to_work <{cons}> .
                    {language_filter}
                    ?s cdm:manifestation_manifests_expression ?expr .
                    ?s ?p ?o .
                }}""",

            # 4. Their items
            "items": f"""
                PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
                SELECT ?s ?p ?o WHERE {{
                    ?expr cdm:expression_belongs_to_work <{cons}> .
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
                print(f"  {cons} ({level}): query failed: {e}")
                counts[level] = "error"
                continue
            for r in rows:
                g.add((to_rdf(r["s"]), to_rdf(r["p"]), to_rdf(r["o"])))
            counts[level] = len(rows)

        log[cons] = {"law": key, **counts}
        print(f"[{i}/{len(consolidations)}] {key}: {counts}")

    g.serialize(ttl_file, format="turtle")
    print(f"\nSaved {len(g)} triples to {ttl_file} ({len(g) - triples_before} new)")

    with open("eurlex_consolidations_log.json", "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


add_consolidations()
