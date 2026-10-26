import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from rdflib import Graph, URIRef, Namespace, Literal
from rdflib.namespace import RDF, SKOS


#  Downloads the French XML (Formex) version of each EU law, using the item links
#  found in the base TTL file, and uses it to add the articles of each law to the graph.
#  For the old acts without Formex, the HTML version is used instead.
#  The result (base data + articles) is saved in a separate TTL file.


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EURLEX_DATA_DIR = PROJECT_ROOT / "data" / "EUR_Lex"

RAW_DIR = EURLEX_DATA_DIR / "raw"
XML_DIR = RAW_DIR / "XML_Eurlex_laws"
RDF_DIR = EURLEX_DATA_DIR / "rdf"
XML_DIR.mkdir(parents=True, exist_ok=True)
RDF_DIR.mkdir(parents=True, exist_ok=True)

LAWS_JSON = RAW_DIR / "eurlex_laws.json"
ARTICLES_LOG = XML_DIR / "articles_log.json"
BASE_EURLEX_TTL = RDF_DIR / "eurlex_base_data.ttl"
ENRICHED_EURLEX_TTL = RDF_DIR / "eurlex_data_enriched_articles.ttl"

CDM = Namespace("http://publications.europa.eu/ontology/cdm#")
ELI = Namespace("http://data.europa.eu/eli/ontology#")
FRENCH = URIRef("http://publications.europa.eu/resource/authority/language/FRA")

# Class to use when adding the articles, based on the ELI ontology guidelines
SUBDIVISION_SCHEME = URIRef("http://publications.europa.eu/resource/authority/subdivision")
ART_TYPE = URIRef("http://publications.europa.eu/resource/authority/subdivision/ART")

PREFERRED_FORMATS = ["fmx4", "xhtml", "html"]

# Browser-like headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "fr",
}


def articles_from_formex(xml_bytes):

    #  Returns the article numbers of a Formex file, e.g. ["1", "2", "5a"].

    root = ET.fromstring(xml_bytes)

    quoted = set()
    for quote in root.iter("QUOT.STRUCT"):
        for article in quote.iter("ARTICLE"):
            quoted.add(id(article))

    numbers = []
    for article in root.iter("ARTICLE"):
        if id(article) in quoted:
            continue

        identifier = article.get("IDENTIFIER")
        if not identifier:
            continue

        # "001" -> "1", "005A" -> "5a"
        number = identifier.lstrip("0").lower()
        numbers.append(number)

    return numbers


def add_eurlex_articles():

    #  For each law : finds its French manifestations in the base graph, downloads
    #  the files of the best available format, extracts the article numbers,
    #  and adds one ELI subdivision per article to the graph.

    with open(LAWS_JSON, encoding="utf-8") as f:
        laws = json.load(f)

    g = Graph()
    g.parse(BASE_EURLEX_TTL, format="turtle")
    g.bind("eli", ELI)
    g.bind("skos", SKOS)
    triples_before = len(g)

    # Describe the "article" concept once, so the graph says what ART_TYPE is
    g.add((ART_TYPE, RDF.type, SKOS.Concept))
    g.add((ART_TYPE, RDF.type, ELI.SubdivisionType))
    g.add((ART_TYPE, SKOS.inScheme, SUBDIVISION_SCHEME))
    g.add((ART_TYPE, SKOS.prefLabel, Literal("article", lang="fr")))
    g.add((ART_TYPE, SKOS.prefLabel, Literal("article", lang="en")))

    log = {}

    for key, law in laws.items():
        work = URIRef(law["cellar"])
        manifestations = {}
        for expression in g.subjects(CDM.expression_belongs_to_work, work):
            if (expression, CDM.expression_uses_language, FRENCH) not in g:
                continue

            for manifestation in g.subjects(CDM.manifestation_manifests_expression, expression):
                manifestation_type = str(g.value(manifestation, CDM.manifestation_type))
                manifestations[manifestation_type] = manifestation

        # Choose the first available format in the order of preference
        chosen_format = None
        for format_name in PREFERRED_FORMATS:
            if format_name in manifestations:
                chosen_format = format_name
                break

        if chosen_format is None:
            log[key] = {"status": "no French fmx4/xhtml/html manifestation"}
            print(f"{key} : no usable French manifestation")
            continue

        numbers = []   # article numbers found for this law
        files = []     # files saved for this law
        errors = []    # download errors for this law

        # The items of the chosen manifestation are the files to download
        items = sorted(g.subjects(CDM.item_belongs_to_manifestation, manifestations[chosen_format]))

        for item in items:
            url = str(item).replace("http://", "https://")
            response = requests.get(url, headers=HEADERS, timeout=120)

            if response.status_code != 200:
                errors.append(f"{item} : HTTP {response.status_code}")
                continue

            content = response.content
            doc = str(item).split("/")[-1]  # DOC_1, DOC_2

            if chosen_format == "fmx4":

                # Recent acts: the item is a zip of XML files. Older acts: a single XML file.
                # Each file is stored with the name it will have on disk.
                xml_files = []
                if content[:2] == b"PK":
                    archive = zipfile.ZipFile(io.BytesIO(content))
                    for name in archive.namelist():
                        if name.endswith(".xml"):
                            file_name = f"{key}_{doc}_{Path(name).name}"
                            xml_files.append((file_name, archive.read(name)))
                else:
                    file_name = f"{key}_{doc}.xml"
                    xml_files.append((file_name, content))

                for file_name, xml_content in xml_files:
                    path = XML_DIR / file_name
                    path.write_bytes(xml_content)
                    files.append(str(path))

                    for number in articles_from_formex(xml_content):
                        if number not in numbers:
                            numbers.append(number)

            else:
                path = XML_DIR / f"{key}_{doc}.html"
                path.write_bytes(content)
                files.append(str(path))

                # Article titles like <p>Article premier</p> or <p>Article 12</p>
                html = content.decode("utf-8", errors="replace")
                titles = re.findall(r">\s*Article\s+(premier|\d+\s*[a-z]*)\s*<", html, re.IGNORECASE)

                for title in titles:
                    if title.lower() == "premier":
                        number = "1"
                    else:
                        number = title.replace(" ", "").lower()   # "15 bis" -> "15bis"

                    if number not in numbers:
                        numbers.append(number)

        # One ELI subdivision per article, part of the base act
        for number in numbers:
            art = URIRef(f"{work}/art_{number}")
            g.add((art, RDF.type, ELI.LegalResourceSubdivision))
            g.add((art, ELI.is_part_of, work))
            g.add((art, ELI.type_subdivision, ART_TYPE))
            g.add((art, ELI.number, Literal(number)))

        if numbers:
            status = "ok"
        else:
            status = "no articles found"

        log[key] = {
            "status": status,
            "format": chosen_format,
            "articles": len(numbers),
            "files": files,
            "errors": errors,
        }

        message = f"{key} ({chosen_format}) : {len(numbers)} articles"
        if errors:
            message += f", {len(errors)} download errors"
        print(message)

    g.serialize(ENRICHED_EURLEX_TTL, format="turtle")
    print(f"\nSaved {len(g)} triples to {ENRICHED_EURLEX_TTL} "
          f"({triples_before} base + {len(g) - triples_before} new)")

    with open(ARTICLES_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


add_eurlex_articles()