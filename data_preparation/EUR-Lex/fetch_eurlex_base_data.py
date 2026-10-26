import json
import time
from rdflib import Graph, URIRef, Literal, BNode
from SPARQLWrapper import SPARQLWrapper, JSON

ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"
laws_file = "eurlex_laws.json"
output_ttl = "eurlex_base_data.ttl"

# The endpoint never returns more than a fixed number of rows per query (often 10,000),
# so large results are fetched page by page until everything has been retrieved
PAGE_SIZE = 5000


def to_rdf(value):
    """Convert one value from the SPARQL JSON result into an rdflib term."""
    if value["type"] == "uri":
        return URIRef(value["value"])
    if value["type"] == "bnode":
        return BNode(value["value"])
    # "literal" or "typed-literal"
    return Literal(value["value"], lang=value.get("xml:lang"), datatype=value.get("datatype"))


with open(laws_file, encoding="utf-8") as f:
    laws = json.load(f)

g = Graph()
g.bind("cdm", "http://publications.europa.eu/ontology/cdm#")
log = {}

for key, law in laws.items():
    cellar = law.get("cellar")
    if not cellar:
        print(f"{key}: no cellar URI in {laws_file}, skipped (run fill_cellar_uris.py first)")
        log[key] = "no cellar uri"
        continue

    # Outgoing: <law> ?p ?o      Incoming: ?s ?p <law>
    queries = {
        "outgoing": f"SELECT ?p ?o WHERE {{ <{cellar}> ?p ?o }} ORDER BY ?p ?o",
        "incoming": f"SELECT ?s ?p WHERE {{ ?s ?p <{cellar}> }} ORDER BY ?s ?p",
    }
    law_uri = URIRef(cellar)
    counts = {}

    for direction, query in queries.items():
        offset, total = 0, 0
        while True:
            sparql = SPARQLWrapper(ENDPOINT)
            sparql.setQuery(f"{query} LIMIT {PAGE_SIZE} OFFSET {offset}")
            sparql.setReturnFormat(JSON)
            sparql.setTimeout(300)

            try:
                rows = sparql.query().convert()["results"]["bindings"]
            except Exception as e:
                print(f"{key} ({direction}): query failed at offset {offset}: {e}")
                counts[direction + "_error"] = str(e)
                break

            for r in rows:
                if direction == "outgoing":
                    g.add((law_uri, to_rdf(r["p"]), to_rdf(r["o"])))
                else:
                    g.add((to_rdf(r["s"]), to_rdf(r["p"]), law_uri))

            total += len(rows)
            if len(rows) < PAGE_SIZE:  # last page reached
                break
            offset += PAGE_SIZE
            time.sleep(1)  # be gentle with the public endpoint

        counts[direction] = total

    log[key] = counts
    print(f"{key}: {counts.get('outgoing', 0)} outgoing, {counts.get('incoming', 0)} incoming")

g.serialize(output_ttl, format="turtle")
print(f"\nSaved {len(g)} triples to {output_ttl}")

with open("eurlex_base_data_log.json", "w", encoding="utf-8") as f:
    json.dump(log, f, indent=2, ensure_ascii=False)
