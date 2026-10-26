import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
import requests
from rdflib import Graph, URIRef, Namespace
from rdflib.namespace import RDF
from SPARQLWrapper import SPARQLWrapper, JSON


#  Retrieves the French XML version of each Fedlex act, stores the files, and uses
#  them to complete the base graph with the articles missing from the Fedlex KG.
#  The french version of the law is used for adding the articles only. Other laws
#  in different languages are still available through the RDF DB. 


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEDLEX_DATA_DIR = PROJECT_ROOT / "data" / "Fedlex"

LAWS_JSON = FEDLEX_DATA_DIR / "raw" / "fedlex_laws.json"
XML_LAWS_DIR = FEDLEX_DATA_DIR / "raw" / "XML_Fedlex_laws"
XML_LOG_JSON = XML_LAWS_DIR / "download_log.json"

BASE_FEDLEX_TTL = FEDLEX_DATA_DIR / "rdf" / "fedlex_base_data.ttl"
ENRICHED_FEDLEX_TTL = FEDLEX_DATA_DIR / "rdf" / "fedlex_data_enriched_articles.ttl"

XML_LAWS_DIR.mkdir(parents=True, exist_ok=True)

ENDPOINT = "https://fedlex.data.admin.ch/sparqlendpoint"

JOLUX = Namespace("http://data.legilux.public.lu/resource/ontology/jolux#")
AKN_NAMESPACE = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN = {"akn": AKN_NAMESPACE}


def get_french_xml():

    
    #  For each law listed in fedlex_laws.json 8OC version) we follow 
    #  the Fedlex KG (act -> expression -> manifestation -> file) to 
    #  find the French XML file and download it locally 


    with open(LAWS_JSON, encoding="utf-8") as f:
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
        results = sparql.query().convert()
        rows = results["results"]["bindings"]


        # Listing all the available manifestation of the current law (all languages and formats)
        urls = []
        for row in rows:
            urls.append(row["url"]["value"])

        # Keep only the french version by looking at the manifestation's URL
        xml_urls = []
        for url in urls:
            if "/fr/xml/" in url:
                xml_urls.append(url)


        # If the french + XML version of the law is not available, log the available french version (but don't download it)
        if not xml_urls:

            fr_available_files = []
            for url in urls:
                if "/fr/" in url:
                    fr_available_files.append(url)

            log[key] = {
                "status": "no french XML found",
                "oc": oc,
                "french_files_available": fr_available_files,
            }
            print(f"{key} : no French XML found")
            continue

        url = xml_urls[0]
        response = requests.get(url) # Download XML

        if response.status_code == 200:
            path = XML_LAWS_DIR / f"{key}_fr.xml"
            path.write_bytes(response.content)
            log[key] = {"status": "downloaded", "oc": oc, "url": url, "file": str(path)}
            print(f"{key} : downloaded")
        else:
            log[key] = {"status": f"download failed ({response.status_code})", "oc": oc, "url": url}
            print(f"{key} : download failed ({response.status_code})")

    with open(XML_LOG_JSON, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)



def add_missing_articles():


    #  Reads every XML file, finds the top-level articles of each act and adds
    #  the ones missing from the base graph, linked to the CC version of the law.
    #  The result (base data + added articles) is saved in a separate TTL file.


    g = Graph()
    g.parse(BASE_FEDLEX_TTL, format="turtle")
    triples_before = len(g)

    # Fedlex writes inserted articles without underscore before the suffix : art_13_a -> art_13a
    # This pattern finds those underscores, so we can remove them to compare these articles numbers 
    # with the existing ones in the fedlex KG. 
    underscore_before_letter = re.compile(r"(?<=[0-9a-z])_(?=[a-z])")

    # Articles already in the graph
    existing_articles = set()
    for subdivision in g.subjects(JOLUX.legalResourceSubdivisionIsPartOf, None):
        existing_articles.add(str(subdivision))

    # Pattern for the top level article in XML (eId)
    top_level_article = re.compile(r"^art_[0-9a-z_]+$")

    for xml_file in (XML_LAWS_DIR.glob("*.xml")):

        root = ET.parse(xml_file).getroot()
        xml_uri = root.find(".//akn:FRBRWork/akn:FRBRuri", AKN).get("value")

        cc_uri = re.sub(r"/eli/oc/", "/eli/cc/", xml_uri)
        cc_uri = re.sub(r"/\d{8}$", "", cc_uri)
        base_law_uri = URIRef(cc_uri)

        found = 0
        added = 0

        for article in root.iter(f"{{{AKN_NAMESPACE}}}article"):
            eid = article.get("eId")
            if not eid or not top_level_article.match(eid):
                continue
            found += 1

            # Write the article identifier the Fedlex way (art_13_a -> art_13a)
            fedlex_eid = underscore_before_letter.sub("", eid)
            art = URIRef(f"{cc_uri}/{fedlex_eid}")

            if str(art) in existing_articles:
                continue

            g.add((art, RDF.type, JOLUX.LegalResourceSubdivision))
            g.add((art, JOLUX.legalResourceSubdivisionIsPartOf, base_law_uri))
            g.add((art, JOLUX.legalResourceSubdivisionType, URIRef("https://fedlex.data.admin.ch/vocabulary/subdivision-type/art")))

            existing_articles.add(str(art))
            added += 1

        print(f"{xml_file.name} : {found} articles in XML, {found - added} already in Fedlex, {added} added")

    g.serialize(ENRICHED_FEDLEX_TTL, format="turtle")
    print(f"\nSaved {len(g)} triples to {ENRICHED_FEDLEX_TTL} "
          f"({triples_before} base + {len(g) - triples_before} new)")


get_french_xml()
add_missing_articles()