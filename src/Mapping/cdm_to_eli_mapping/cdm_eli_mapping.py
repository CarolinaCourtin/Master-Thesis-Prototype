from pathlib import Path
from rdflib import Graph, Namespace
from rdflib.namespace import split_uri
import re
import json
from rapidfuzz import process, fuzz

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CURRENT_FOLDER = Path(__file__).resolve().parents[0]

EURLEX_DATA_DIR = PROJECT_ROOT / "data" / "EUR_Lex"
EURLEX_TTL = EURLEX_DATA_DIR / "rdf" / "eurlex_base_data.ttl"

CDM_DATA_DIR = PROJECT_ROOT / "data" / "EUR_Lex" / "rdf" / "cdm-4.17.0"
CDM_RDF = CDM_DATA_DIR / "cdm.rdf"

ELI_DATA_DIR = PROJECT_ROOT / "data" / "ELI-release"
ELI_OWL = ELI_DATA_DIR / "eli.owl"

CDM_RESOURCES = CURRENT_FOLDER / "cdm_resources.json"
EURLEX_RESOURCES = CURRENT_FOLDER / "eurlex_resources.json"
ELI_RESOURCES = CURRENT_FOLDER / "eli_resources.json"

CDM_ELI_MAPPING_RESULTS = CURRENT_FOLDER / "mapping_results.json"

CDM = Namespace("http://publications.europa.eu/ontology/cdm#")
ELI = Namespace("http://data.europa.eu/eli/ontology#")


def prep_cdm_resources(onto_file, format, source):
    # source = "data"     -> EURLEX_TTL : classes/properties used in the local KG laws
    # source = "ontology" -> CDM_RDF    : classes/properties declared in the WHOLE CDM ontology

    g_cdm = Graph()
    g_cdm.parse(onto_file, format=format)   # ttl or xml (for RDF files)

    cdm_classes_clean = {}
    cdm_properties_clean = {}

    file_name=None

    if source == "data":
        cdm_classes_query = """
        SELECT DISTINCT ?c
        WHERE { ?s a ?c }
        """
        cdm_properties_query = """
        SELECT DISTINCT ?p
        WHERE { ?s ?p ?o }
        """

        file_name = EURLEX_RESOURCES

    else:   
        cdm_classes_query = """
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        SELECT DISTINCT ?c
        WHERE { ?c a owl:Class . }
        """
        cdm_properties_query = """
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        SELECT DISTINCT ?p
        WHERE {
          VALUES ?type { owl:ObjectProperty owl:DatatypeProperty }
          ?p a ?type .
        }
        """

        file_name=CDM_RESOURCES

    cdm_classes = g_cdm.query(cdm_classes_query)
    cdm_properties = g_cdm.query(cdm_properties_query)


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

    with open(file_name, "w", encoding="utf-8") as f:
        json.dump({"classes": cdm_classes_clean,
                "properties": cdm_properties_clean},
                f, indent=2, ensure_ascii=False)

    return cdm_classes_clean, cdm_properties_clean


def prep_eli_resources():

    g_eli = Graph()
    g_eli.parse(ELI_OWL, format="xml")

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


def mapping(dict_vocab_1, dict_vocab_2, results_file, method, limit, cutoff):

    results = []
    for uri, name in dict_vocab_1.items(): # eli : one by one 
        matches = process.extract(name, dict_vocab_2,scorer=method,limit=limit, score_cutoff=cutoff)
        results.append({
            "uri": uri,
            "name": name,
            "candidates": [{"candidate_uri": cand_uri, "candidate_name": cand_name, "score": round(score, 1)}
                        for cand_name, score, cand_uri in matches],
        })

    json.dump(results, open(results_file, "w"), indent=2, ensure_ascii=False)

cdm_classes, cdm_properties = prep_cdm_resources(onto_file=CDM_RDF, format="xml", source="ontology")
eurlex_classes, eurlex_properties = prep_cdm_resources(onto_file=EURLEX_TTL, format="turtle", source="data")

eli_classes, eli_properties = prep_eli_resources()


mapping(eli_classes, cdm_classes, CURRENT_FOLDER / "eli_cdm_ontology_classes_token_set_matching_results.json", method=fuzz.token_set_ratio, limit=10, cutoff=60)
mapping(eli_classes, eurlex_classes, CURRENT_FOLDER / "eli_cdm_data_classes_token_set_matching_results.json", method=fuzz.token_set_ratio, limit=10, cutoff=60)

mapping(eli_properties, cdm_properties, CURRENT_FOLDER / "eli_cdm_ontology_properties_token_set_matching_results.json", method=fuzz.token_set_ratio, limit=10, cutoff=60)
mapping(eli_properties, eurlex_properties, CURRENT_FOLDER / "eli_cdm_data_properties_token_set_matching_results.json", method=fuzz.token_set_ratio, limit=10, cutoff=60)