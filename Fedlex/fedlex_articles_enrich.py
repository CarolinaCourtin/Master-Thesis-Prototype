import requests
import json
from pathlib import Path
from SPARQLWrapper import SPARQLWrapper, JSON
import re
import xml.etree.ElementTree as ET
from rdflib import Graph, URIRef, Namespace
from rdflib.namespace import RDF

'''
Script that retrieves the XML version of each act and use them to store them 
along with completing the base graph with the missing articles for each law

Download the French XML version of each act (OC) listed in fedlex_laws.json

'''

def get_french_xml():

    ENDPOINT = "https://fedlex.data.admin.ch/sparqlendpoint"
    output_dir = Path("XML_Fedlex_laws")
    output_dir.mkdir(exist_ok=True)

    with open("fedlex_laws.json", encoding="utf-8") as f:
        laws = json.load(f)

    log = {}

    for key, law in laws.items():
        oc = law["oc"]
        if not oc:
            log[key] = {"status": "no OC uri"}
            continue

        query = f"""
        PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
        SELECT ?url WHERE {{
            <{oc}> jolux:isRealizedBy ?expression .
            ?expression jolux:isEmbodiedBy ?manifestation .
            ?manifestation jolux:isExemplifiedBy ?url .
        }}
        """
        sparql = SPARQLWrapper(ENDPOINT)
        sparql.setQuery(query)
        sparql.setReturnFormat(JSON)
        results = sparql.query().convert()["results"]["bindings"]
        urls = [r["url"]["value"] for r in results]


        xml_urls = [u for u in urls if "/fr/xml/" in u]

        if not xml_urls:
            french_files = [u for u in urls if "/fr/" in u]
            log[key] = {"status": "no french XML found", "oc": oc, "french_files_available": french_files}
            print(f"{key}: no French XML found")
            continue

        url = xml_urls[0]
        response = requests.get(url)

        if response.status_code == 200:
            path = output_dir / f"{key}_fr.xml"
            path.write_bytes(response.content)
            log[key] = {"status": "downloaded", "oc": oc, "url": url, "file": str(path)}
            print(f"{key}: downloaded")
        else:
            log[key] = {"status": f"download failed ({response.status_code})", "oc": oc, "url": url}
            print(f"{key}: download failed ({response.status_code})")

    with open(output_dir / "download_log.json", "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    print("Done, log saved in", output_dir / "download_log.json")




def add_missing_articles():

    xml_dir = Path("XML_Fedlex_laws")
    base_ttl = "fedlex_base_data.ttl"
    output_ttl = "fedlex_data_enriched_articles.ttl"

    JOLUX = Namespace("http://data.legilux.public.lu/resource/ontology/jolux#")
    AKN = {"akn": "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"}

    g = Graph()
    g.parse(base_ttl, format="turtle")
    triples_before = len(g)

    art_type = None
    for sub, typ in g.subject_objects(JOLUX.legalResourceSubdivisionType):
        if str(typ).endswith("/art") and str(sub).split("/")[-1].startswith("art_"):
            art_type = typ
            break
    print("Article type URI:", art_type)

    # Top-level articles only
    top_level_article = re.compile(r"^art_[0-9a-z_]+$")

    for xml_file in sorted(xml_dir.glob("*.xml")):
        root = ET.parse(xml_file).getroot()

        xml_uri = root.find(".//akn:FRBRWork/akn:FRBRuri", AKN).get("value")

        cc_uri = re.sub(r"/eli/oc/", "/eli/cc/", xml_uri)
        cc_uri = re.sub(r"/\d{8}$", "", cc_uri)
        law = URIRef(cc_uri)

        found, added = 0, 0
        for article in root.iter("{http://docs.oasis-open.org/legaldocml/ns/akn/3.0}article"):
            eid = article.get("eId")
            if not eid or not top_level_article.match(eid):
                continue
            found += 1

            art = URIRef(f"{cc_uri}/{eid}")

            if (art, JOLUX.legalResourceSubdivisionIsPartOf, None) in g:
                continue

            g.add((art, RDF.type, JOLUX.LegalResourceSubdivision))
            g.add((art, JOLUX.legalResourceSubdivisionIsPartOf, law))
            if art_type is not None:
                g.add((art, JOLUX.legalResourceSubdivisionType, art_type))
            added += 1

        print(f"{xml_file.name}: {found} articles in XML, {found - added} already in Fedlex, {added} added")

    g.serialize(output_ttl, format="turtle")
    print(f"\nSaved {len(g)} triples to {output_ttl} "
          f"({triples_before} base + {len(g) - triples_before} new)")

add_missing_articles()