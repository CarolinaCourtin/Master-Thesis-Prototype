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


CDM = Namespace("http://publications.europa.eu/ontology/cdm#")
ELI = Namespace("http://data.europa.eu/eli/ontology#")


def prep_resources(onto_file, format, results_output_file):

    """
    This function takes as an input the desired ontology and process it 
    to list all the defined classes and properties, along with their
    respectif URI, cleaned name, label and comment. The lists of ressources
    are then stored into a JSON file.
    
    """

    g = Graph()
    g.parse(onto_file, format) 

    results = {
        "classes" : [],
        "properties" : []
    }

    classes_clean = {}
    properties_clean = {}


    classes_query = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT DISTINCT ?c ?label ?comment
    WHERE { 
    ?c a owl:Class .
    ?c rdfs:label ?label .
    ?c rdfs:comment ?comment .
        }
    """
    properties_query = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT DISTINCT ?p ?label ?comment
    WHERE {
        VALUES ?type { owl:ObjectProperty owl:DatatypeProperty }
        ?p a ?type .
        ?p rdfs:label ?label .
        ?p rdfs:comment ?comment .
    }
    """

    classes = g.query(classes_query)
    properties = g.query(properties_query)

    # Clean the name of the classes and properties before computing the fuzzy matching scores
    for c in classes:              
        ns, local = split_uri(c.c)
        class_clean = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', local)
        class_clean = re.sub(r'[_\-]+', ' ', class_clean)
        class_clean = class_clean.lower().strip()

        classes_clean[c.c] = class_clean

        results["classes"].append({
        "uri": c.c,
        "name": class_clean,
        "label": c.label,
        "comment": c.comment
    })

    for prop in properties:              
        ns, local = split_uri(prop.p)
        prop_clean = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', local)
        prop_clean = re.sub(r'[_\-]+', ' ', prop_clean)
        prop_clean = prop_clean.lower().strip()

        properties_clean[prop.p] = prop_clean

        results["properties"].append({
        "uri": prop.p,
        "name": prop_clean,
        "label": prop.label,
        "comment": prop.comment
    })

    with open(CURRENT_FOLDER / results_output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return classes_clean, properties_clean


def fuzzy_mapping(vocab_1, vocab_2, results_file, method, limit, cutoff):

    """
    This function takes as an input two dictionnaires containing the 
    set of classes or properties from the two ontologies we want to 
    compare using fuzzy matching. The parameters of the fuzzy matching
    method can be changed using the functions input. 
    
    """

    results = []
    for uri, name in vocab_1.items(): # eli : one by one 
        matches = process.extract(name, vocab_2,scorer=method,limit=limit, score_cutoff=cutoff)
        results.append({
            "uri": uri,
            "name": name,
            "candidates": [{"candidate_uri": cand_uri, "candidate_name": cand_name,"score": round(score, 1)}
                           for cand_name, score, cand_uri in matches],
        })


    with open(CURRENT_FOLDER / results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


cdm_classes, cdm_properties = prep_resources(onto_file=CDM_RDF, format="xml", results_output_file="cdm_ressources.json")
eli_classes, eli_properties = prep_resources(onto_file=ELI_OWL, format="xml", results_output_file="eli_ressources.json")

fuzzy_mapping(eli_classes, cdm_classes, "eli_cdm_classes_token_set_matching_results.json", method=fuzz.token_set_ratio, limit=10, cutoff=60)
fuzzy_mapping(eli_properties, cdm_properties, "eli_cdm_properties_token_set_matching_results.json", method=fuzz.token_set_ratio, limit=10, cutoff=60)