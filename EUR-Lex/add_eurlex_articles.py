import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from rdflib import Graph, URIRef, Namespace, Literal
from rdflib.namespace import RDF, SKOS

laws_file = "eurlex_laws.json"
base_ttl = "eurlex_base_data.ttl"
output_ttl = "eurlex_data_enriched_articles.ttl"
xml_dir = Path("xml eurlex laws")
xml_dir.mkdir(exist_ok=True)

CDM = Namespace("http://publications.europa.eu/ontology/cdm#")
ELI = Namespace("http://data.europa.eu/eli/ontology#")
FRENCH = URIRef("http://publications.europa.eu/resource/authority/language/FRA")

# "Article" concept of the EU Publications Office subdivision table
# (the value list recommended by the ELI ontology for eli:type_subdivision)
SUBDIVISION_SCHEME = URIRef("http://publications.europa.eu/resource/authority/subdivision")
ART_TYPE = URIRef("http://publications.europa.eu/resource/authority/subdivision/ART")


# Browser-like headers: the EU server can refuse plain script requests with HTTP 403
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "fr",
}


def articles_from_formex(xml_bytes):
    """
    Returns the article numbers of a Formex file, e.g. ["1", "2", "5a"].
    Articles quoted inside amending provisions (QUOT.STRUCT) belong to OTHER acts
    and are ignored.
    """
    root = ET.fromstring(xml_bytes)

    quoted = set()
    for quote in root.iter("QUOT.STRUCT"):
        for article in quote.iter("ARTICLE"):
            quoted.add(id(article))

    numbers = []
    for article in root.iter("ARTICLE"):
        if id(article) in quoted or not article.get("IDENTIFIER"):
            continue
        numbers.append(article.get("IDENTIFIER").lstrip("0").lower())
    return numbers


with open(laws_file, encoding="utf-8") as f:
    laws = json.load(f)

g = Graph()
g.parse(base_ttl, format="turtle")
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

    # French expression of the base act -> its manifestations, by format
    manifestations = {}
    for expr in g.subjects(CDM.expression_belongs_to_work, work):
        if (expr, CDM.expression_uses_language, FRENCH) in g:
            for manif in g.subjects(CDM.manifestation_manifests_expression, expr):
                manifestations[str(g.value(manif, CDM.manifestation_type))] = manif

    # Formex XML if available, otherwise HTML (old acts)
    fmt = next((f for f in ["fmx4", "xhtml", "html"] if f in manifestations), None)
    if fmt is None:
        log[key] = {"status": "no French fmx4/xhtml/html manifestation"}
        print(f"{key}: no usable French manifestation")
        continue

    numbers, files, errors = [], [], []

    for item in sorted(g.subjects(CDM.item_belongs_to_manifestation, manifestations[fmt])):
        response = requests.get(str(item).replace("http://", "https://"), headers=HEADERS, timeout=120)
        if response.status_code != 200:
            errors.append(f"{item}: HTTP {response.status_code}")
            continue
        content = response.content
        doc = str(item).rsplit("/", 1)[-1]  # DOC_1, DOC_2...

        if fmt == "fmx4":
            # Recent acts: the item is a zip of XML files. Older acts: a single XML file
            if content[:2] == b"PK":
                z = zipfile.ZipFile(io.BytesIO(content))
                xml_files = [(name, z.read(name)) for name in z.namelist() if name.endswith(".xml")]
            else:
                xml_files = [(f"{doc}.xml", content)]

            for name, xml_content in xml_files:
                path = xml_dir / f"{key}_{doc}_{Path(name).name}"
                path.write_bytes(xml_content)
                files.append(str(path))
                for n in articles_from_formex(xml_content):
                    if n not in numbers:
                        numbers.append(n)
        else:
            path = xml_dir / f"{key}_{doc}.html"
            path.write_bytes(content)
            files.append(str(path))
            # Article titles like <p>Article premier</p> or <p>Article 12</p>
            html = content.decode("utf-8", errors="replace")
            for found in re.findall(r">\s*Article\s+(premier|\d+\s*[a-z]*)\s*<", html, re.IGNORECASE):
                n = "1" if found.lower() == "premier" else found.replace(" ", "").lower()
                if n not in numbers:
                    numbers.append(n)

    # One ELI subdivision per article, part of the base act
    for n in numbers:
        art = URIRef(f"{work}/art_{n}")
        g.add((art, RDF.type, ELI.LegalResourceSubdivision))
        g.add((art, ELI.is_part_of, work))
        g.add((art, ELI.type_subdivision, ART_TYPE))
        g.add((art, ELI.number, Literal(n)))

    log[key] = {"status": "ok" if numbers else "no articles found", "format": fmt,
                "articles": len(numbers), "files": files, "errors": errors}
    print(f"{key} ({fmt}): {len(numbers)} articles" + (f", {len(errors)} download errors" if errors else ""))

g.serialize(output_ttl, format="turtle")
print(f"\nSaved {len(g)} triples to {output_ttl} ({triples_before} base + {len(g) - triples_before} new)")

with open(xml_dir / "articles_log.json", "w", encoding="utf-8") as f:
    json.dump(log, f, indent=2, ensure_ascii=False)
