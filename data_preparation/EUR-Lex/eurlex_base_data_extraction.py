import json
import time
from pathlib import Path
from rdflib import Graph, URIRef, Literal, BNode, Namespace
from SPARQLWrapper import SPARQLWrapper, JSON

ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EURLEX_DATA_DIR = PROJECT_ROOT / "data" / "EUR_Lex"

RAW_DIR = EURLEX_DATA_DIR / "raw"
RDF_DIR = EURLEX_DATA_DIR / "rdf"
RAW_DIR.mkdir(parents=True, exist_ok=True)
RDF_DIR.mkdir(parents=True, exist_ok=True)

LAWS_JSON = RAW_DIR / "eurlex_laws.json"
BASE_EURLEX_TTL = RDF_DIR / "eurlex_base_data.ttl"
BASE_EURLEX_LOG = RAW_DIR / "eurlex_base_data_log.json"

CDM = Namespace("http://publications.europa.eu/ontology/cdm#")
LANGUAGE_URI = "http://publications.europa.eu/resource/authority/language/"

# The endpoint never returns more than a fixed number of rows per query,
# so large results are fetched page by page until everything has been retrieved
PAGE_SIZE = 5000


def get_eurlex_base_resources():


    #  For each EU law, this function retrieves its metadata
    #  by exploring the set of incoming and outgoing relations
    #  attached to this resource.


    with open(LAWS_JSON, encoding="utf-8") as f:
        laws = json.load(f)

    g = Graph()
    if BASE_EURLEX_TTL.exists():
        g.parse(BASE_EURLEX_TTL, format="turtle")
    g.bind("cdm", str(CDM))
    triples_before = len(g)

    log = {}

    for key, law in laws.items():
        cellar = law.get("cellar")
        if not cellar:
            log[key] = "no cellar uri"
            continue

        law_uri = URIRef(cellar)

        outgoing_query = f"""
        SELECT ?p ?o WHERE {{
            <{cellar}> ?p ?o .
        }}
        ORDER BY ?p ?o
        """
        incoming_query = f"""
        SELECT ?s ?p WHERE {{
            ?s ?p <{cellar}> .
        }}
        ORDER BY ?s ?p
        """

        queries = {
            "outgoing": outgoing_query,
            "incoming": incoming_query,
        }
        counts = {}

        for direction, query in queries.items():
            offset = 0
            total = 0

            while True:
                sparql = SPARQLWrapper(ENDPOINT)
                sparql.setQuery(f"{query} LIMIT {PAGE_SIZE} OFFSET {offset}")
                sparql.setReturnFormat(JSON)
                sparql.setTimeout(300)

                try:
                    results = sparql.query().convert()
                    rows = results["results"]["bindings"]
                except Exception as e:
                    print(f"{key} ({direction}) : query failed at offset {offset} : {e}")
                    counts[f"{direction}_error"] = str(e)
                    break

                for row in rows:
                    # Each row gives two of the three parts of the triple (?p ?o or ?s ?p).
                    # The missing part is the law itself.
                    triple = {}
                    for position in ["s", "p", "o"]:
                        if position not in row:
                            triple[position] = law_uri
                            continue

                        # Convert the value from the SPARQL JSON result into an rdflib term
                        value = row[position]
                        if value["type"] == "uri":
                            triple[position] = URIRef(value["value"])
                        elif value["type"] == "bnode":
                            triple[position] = BNode(value["value"])
                        else:
                            triple[position] = Literal(
                                value["value"],
                                lang=value.get("xml:lang"),
                                datatype=value.get("datatype"),
                            )

                    g.add((triple["s"], triple["p"], triple["o"]))

                total += len(rows)

                # A page with fewer rows than PAGE_SIZE is the last one
                if len(rows) < PAGE_SIZE:
                    break

                offset += PAGE_SIZE
                time.sleep(1)

            counts[direction] = total

        log[key] = counts

        outgoing = counts.get("outgoing", 0)
        incoming = counts.get("incoming", 0)
        print(f"{key} : {outgoing} outgoing, {incoming} incoming")

    g.serialize(BASE_EURLEX_TTL, format="turtle")
    print(f"\nSaved {len(g)} triples to {BASE_EURLEX_TTL} ({len(g) - triples_before} new)")

    with open(BASE_EURLEX_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def add_eurlex_expressions_manifestations_items(language=None):


    #  This function adds to the base TTL file the expressions, manifestations
    #  and items of each law (not of the consolidations) :
    #    expression using cdm:expression_belongs_to_work
    #    manifestation using cdm:manifestation_manifests_expression
    #    item using cdm:item_belongs_to_manifestation-->  
    #  language: None for every language, or a 3-letter EU code such as "FRA".


    with open(LAWS_JSON, encoding="utf-8") as f:
        laws = json.load(f)

    g = Graph()
    g.parse(BASE_EURLEX_TTL, format="turtle")
    triples_before = len(g)

    # Optional filter on the language of the expressions
    language_filter_on_s = ""
    language_filter_on_expr = ""
    if language:
        language_filter_on_s = f"?s cdm:expression_uses_language <{LANGUAGE_URI}{language}> ."
        language_filter_on_expr = f"?expr cdm:expression_uses_language <{LANGUAGE_URI}{language}> ."

    for key, law in laws.items():
        cellar = law.get("cellar")
        if not cellar:
            print(f"{key} : no cellar URI, skipped")
            continue

        # expressions of the law
        expressions_query = f"""
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        SELECT ?s ?p ?o WHERE {{
            ?s cdm:expression_belongs_to_work <{cellar}> .
            {language_filter_on_s}
            ?s ?p ?o .
        }}
        ORDER BY ?s ?p ?o
        """

        # manifestations of these expressions
        manifestations_query = f"""
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        SELECT ?s ?p ?o WHERE {{
            ?expr cdm:expression_belongs_to_work <{cellar}> .
            {language_filter_on_expr}
            ?s cdm:manifestation_manifests_expression ?expr .
            ?s ?p ?o .
        }}
        ORDER BY ?s ?p ?o
        """

        # items of these manifestations
        items_query = f"""
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        SELECT ?s ?p ?o WHERE {{
            ?expr cdm:expression_belongs_to_work <{cellar}> .
            {language_filter_on_expr}
            ?manif cdm:manifestation_manifests_expression ?expr .
            ?s cdm:item_belongs_to_manifestation ?manif .
            ?s ?p ?o .
        }}
        ORDER BY ?s ?p ?o
        """

        queries = {
            "expressions": expressions_query,
            "manifestations": manifestations_query,
            "items": items_query,
        }
        counts = {}

        for level, query in queries.items():
            offset = 0
            total = 0

            while True:
                sparql = SPARQLWrapper(ENDPOINT)
                sparql.setQuery(f"{query} LIMIT {PAGE_SIZE} OFFSET {offset}")
                sparql.setReturnFormat(JSON)
                sparql.setTimeout(300)

                try:
                    results = sparql.query().convert()
                    rows = results["results"]["bindings"]
                except Exception as e:
                    print(f"{key} ({level}) : query failed at offset {offset} : {e}")
                    counts[f"{level}_error"] = str(e)
                    break

                for row in rows:
                    # Here every row gives the three parts of the triple (?s ?p ?o)
                    triple = {}
                    for position in ["s", "p", "o"]:

                        # Convert the value from the SPARQL JSON result into an rdflib term
                        value = row[position]
                        if value["type"] == "uri":
                            triple[position] = URIRef(value["value"])
                        elif value["type"] == "bnode":
                            triple[position] = BNode(value["value"])
                        else:
                            triple[position] = Literal(
                                value["value"],
                                lang=value.get("xml:lang"),
                                datatype=value.get("datatype"),
                            )

                    g.add((triple["s"], triple["p"], triple["o"]))

                total += len(rows)

                if len(rows) < PAGE_SIZE:
                    break

                offset += PAGE_SIZE
                time.sleep(1)

            counts[level] = total

        print(f"{key} : {counts}")

    g.serialize(BASE_EURLEX_TTL, format="turtle")
    print(f"\nSaved {len(g)} triples to {BASE_EURLEX_TTL} ({len(g) - triples_before} new)")


def add_eurlex_consolidations(language=None):


    #  This function adds to the base TTL file the full data of the consolidated versions of each law :
    #  their metadata, expressions, manifestations and items.
    #  Consolidations of the laws are kept using the relation cdm:act_consolidated_based_on_resource_legal.
    #  language: None for every language, or a 3-letter EU code such as "FRA".


    with open(LAWS_JSON, encoding="utf-8") as f:
        laws = json.load(f)

    g = Graph()
    g.parse(BASE_EURLEX_TTL, format="turtle")
    triples_before = len(g)

    # Find the consolidations already linked to the laws in the base TTL file
    consolidations = {}
    for key, law in laws.items():
        cellar = law.get("cellar")
        if not cellar:
            continue
        law_uri = URIRef(cellar)

        for consolidation in g.subjects(CDM.act_consolidated_based_on_resource_legal, law_uri):
            consolidations[str(consolidation)] = key

    print(f"{len(consolidations)} consolidations to fetch\n")

    # Optional filter on the language of the expressions
    language_filter_on_s = ""
    language_filter_on_expr = ""
    if language:
        language_filter_on_s = f"?s cdm:expression_uses_language <{LANGUAGE_URI}{language}> ."
        language_filter_on_expr = f"?expr cdm:expression_uses_language <{LANGUAGE_URI}{language}> ."

    number = 0

    for cons, key in consolidations.items():
        number += 1
        cons_uri = URIRef(cons)

        # The consolidation itself (its metadata)
        metadata_query = f"""
        SELECT ?p ?o WHERE {{
            <{cons}> ?p ?o .
        }}
        ORDER BY ?p ?o
        """

        # expressions
        expressions_query = f"""
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        SELECT ?s ?p ?o WHERE {{
            ?s cdm:expression_belongs_to_work <{cons}> .
            {language_filter_on_s}
            ?s ?p ?o .
        }}
        ORDER BY ?s ?p ?o
        """

        # manifestations
        manifestations_query = f"""
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        SELECT ?s ?p ?o WHERE {{
            ?expr cdm:expression_belongs_to_work <{cons}> .
            {language_filter_on_expr}
            ?s cdm:manifestation_manifests_expression ?expr .
            ?s ?p ?o .
        }}
        ORDER BY ?s ?p ?o
        """

        # items
        items_query = f"""
        PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
        SELECT ?s ?p ?o WHERE {{
            ?expr cdm:expression_belongs_to_work <{cons}> .
            {language_filter_on_expr}
            ?manif cdm:manifestation_manifests_expression ?expr .
            ?s cdm:item_belongs_to_manifestation ?manif .
            ?s ?p ?o .
        }}
        ORDER BY ?s ?p ?o
        """

        queries = {
            "metadata": metadata_query,
            "expressions": expressions_query,
            "manifestations": manifestations_query,
            "items": items_query,
        }
        counts = {}

        for level, query in queries.items():
            offset = 0
            total = 0

            while True:
                sparql = SPARQLWrapper(ENDPOINT)
                sparql.setQuery(f"{query} LIMIT {PAGE_SIZE} OFFSET {offset}")
                sparql.setReturnFormat(JSON)
                sparql.setTimeout(300)

                try:
                    results = sparql.query().convert()
                    rows = results["results"]["bindings"]
                except Exception as e:
                    print(f"  {cons} ({level}) : query failed at offset {offset} : {e}")
                    counts[f"{level}_error"] = str(e)
                    break

                for row in rows:
                    triple = {}
                    for position in ["s", "p", "o"]:
                        if position not in row:
                            triple[position] = cons_uri
                            continue

                        # Convert the value from the SPARQL JSON result into an rdflib term
                        value = row[position]
                        if value["type"] == "uri":
                            triple[position] = URIRef(value["value"])
                        elif value["type"] == "bnode":
                            triple[position] = BNode(value["value"])
                        else:
                            triple[position] = Literal(
                                value["value"],
                                lang=value.get("xml:lang"),
                                datatype=value.get("datatype"),
                            )

                    g.add((triple["s"], triple["p"], triple["o"]))

                total += len(rows)

                if len(rows) < PAGE_SIZE:
                    break

                offset += PAGE_SIZE
                time.sleep(1)

            counts[level] = total

        print(f"[{number}/{len(consolidations)}] {key} : {counts}")

    g.serialize(BASE_EURLEX_TTL, format="turtle")
    print(f"\nSaved {len(g)} triples to {BASE_EURLEX_TTL} ({len(g) - triples_before} new)")



get_eurlex_base_resources()
add_eurlex_expressions_manifestations_items()  
add_eurlex_consolidations()                   