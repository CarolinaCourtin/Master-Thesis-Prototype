from pathlib import Path
from rdflib import Graph, URIRef, Namespace
from rdflib.namespace import split_uri
import re
import json

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CURRENT_FOLDER = Path(__file__).resolve().parents[0]
EURLEX_DATA_DIR = PROJECT_ROOT / "data" / "EUR_Lex"
EURLEX_TTL = EURLEX_DATA_DIR / "rdf" / "eurlex_base_data.ttl"

ELI_DATA_DIR = PROJECT_ROOT / "data" / "ELI-release"
ELI_OWL = ELI_DATA_DIR / "eli.owl"

CDM_RESOURCES = CURRENT_FOLDER / "cdm_resources.json"
ELI_RESOURCES = CURRENT_FOLDER / "eli_resources.json"

CDM_ELI_MAPPING_RESULTS = CURRENT_FOLDER / "mapping_results.json"

CDM = Namespace("http://publications.europa.eu/ontology/cdm#")
ELI = Namespace("http://data.europa.eu/eli/ontology#")

g_eurlex = Graph()
g_eurlex.parse(EURLEX_TTL, format="turtle")

g_eli = Graph()
g_eli.parse(ELI_OWL, format="xml")

def prep_cdm_resources():

    cdm_classes_clean = {}
    cdm_properties_clean = {}

    # Retrieve thr set of CDM classes and properties using SPARQL
    cdm_classes_query = """

    PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>

    SELECT DISTINCT ?c
    WHERE { ?s a ?c }

    """

    cdm_properties_query = """

    PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>

    SELECT DISTINCT ?p 
    WHERE { ?s ?p ?o }

    """
    cdm_classes = g_eurlex.query(cdm_classes_query)
    cdm_properties = g_eurlex.query(cdm_properties_query)


    # Clean the name of the classes and properties before computing the fuzzy matching scores
    for c in cdm_classes:
        if c.c in CDM:                
            ns, local = split_uri(c.c)
            class_clean = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', local)
            class_clean = re.sub(r'[_\-]+', ' ', class_clean)
            class_clean = class_clean.lower().strip()

            cdm_classes_clean[c.c] = class_clean

    for prop in cdm_properties:
        if prop.p in CDM:                
            ns, local = split_uri(prop.p)
            prop_clean = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', local)
            prop_clean = re.sub(r'[_\-]+', ' ', prop_clean)
            prop_clean = prop_clean.lower().strip()

            cdm_properties_clean[prop.p] = prop_clean

    with open(CDM_RESOURCES, "w", encoding="utf-8") as f:
        json.dump({"classes": cdm_classes_clean,
                "properties": cdm_properties_clean},
                f, indent=2, ensure_ascii=False)

    return cdm_classes_clean, cdm_properties_clean



def prep_eli_resources():

    eli_classes_clean = {}
    eli_properties_clean = {}

    # Retrieve the set of ELI classes and properties declared in the ontology using SPARQL
    eli_classes_query = """

    PREFIX owl: <http://www.w3.org/2002/07/owl#>

    SELECT DISTINCT ?c
    WHERE { ?c a owl:Class . }

    """

    eli_properties_query = """

    PREFIX owl: <http://www.w3.org/2002/07/owl#>

    SELECT DISTINCT ?p
    WHERE {
      VALUES ?type { owl:ObjectProperty owl:DatatypeProperty }
      ?p a ?type .
    }

    """
    eli_classes = g_eli.query(eli_classes_query)
    eli_properties = g_eli.query(eli_properties_query)


    # Clean the name of the classes and properties before computing the fuzzy matching scores
    for c in eli_classes:
        if c.c in ELI:
            ns, local = split_uri(c.c)
            class_clean = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', local)
            class_clean = re.sub(r'[_\-]+', ' ', class_clean)
            class_clean = class_clean.lower().strip()

            eli_classes_clean[c.c] = class_clean

    for prop in eli_properties:
        if prop.p in ELI:
            ns, local = split_uri(prop.p)
            prop_clean = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', local)
            prop_clean = re.sub(r'[_\-]+', ' ', prop_clean)
            prop_clean = prop_clean.lower().strip()

            eli_properties_clean[prop.p] = prop_clean

    with open(ELI_RESOURCES, "w", encoding="utf-8") as f:
        json.dump({"classes": eli_classes_clean,
                   "properties": eli_properties_clean},
                  f, indent=2, ensure_ascii=False)

    return eli_classes_clean, eli_properties_clean