from pathlib import Path
from rdflib import Graph, Namespace
from rdflib.namespace import split_uri
import re
import json
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CURRENT_FOLDER = Path(__file__).resolve().parents[0]

EURLEX_DATA_DIR = PROJECT_ROOT / "data" / "EUR_Lex"
EURLEX_TTL = EURLEX_DATA_DIR / "rdf" / "eurlex_base_data.ttl"

CDM_DATA_DIR = PROJECT_ROOT / "data" / "EUR_Lex" / "rdf" / "cdm-4.17.0"
CDM_RDF = CDM_DATA_DIR / "cdm.rdf"

ELI_DATA_DIR = PROJECT_ROOT / "data" / "ELI-release"
ELI_OWL = ELI_DATA_DIR / "eli.owl"

CDM = Namespace("http://publications.europa.eu/ontology/cdm#")
ELI = Namespace("http://data.europa.eu/eli/ontology#")


def prep_resources(onto_file, format, namespace, results_output_file):

    """
    This function takes as an input the desired ontology and process it 
    to list all the defined classes and properties, along with their
    respectif URI, cleaned name, label and comment. The lists of ressources
    are then stored into a JSON file.
    
    """

    tqdm.write(f"Parsing {onto_file.name}...")
    g = Graph()
    g.parse(onto_file, format)
    tqdm.write("Running queries...") 

    results = {
        "classes" : [],
        "properties" : []
    }

    classes_clean = {}
    properties_clean = {}
    classes_text = {}          # {uri: "name label comment"} for TF-IDF / embeddings
    properties_text = {}      


    classes_query = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT DISTINCT ?c ?label ?comment
    WHERE { 
    ?c a owl:Class .
    FILTER(isIRI(?c))
    OPTIONAL {?c rdfs:label ?label} .
    OPTIONAL {?c rdfs:comment ?comment} .
        }
    """
    properties_query = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT DISTINCT ?p ?label ?comment
    WHERE {
        VALUES ?type { owl:ObjectProperty owl:DatatypeProperty }
        ?p a ?type .
        OPTIONAL {?p rdfs:label ?label} .
        OPTIONAL {?p rdfs:comment ?comment} .
    }
    """

    classes = g.query(classes_query)
    properties = g.query(properties_query)

    # Clean the name of the classes and properties before computing the fuzzy matching scores
    for c in tqdm(classes, total=len(classes), desc=f"{namespace} classes", unit="cls"): 
        if c.c in namespace:            
            ns, local = split_uri(c.c)
            class_clean = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', local)
            class_clean = re.sub(r'[_\-]+', ' ', class_clean)
            class_clean = class_clean.lower().strip()

            classes_clean[c.c] = class_clean
            classes_text[c.c] = " ".join(str(x) for x in (class_clean, c.label, c.comment) if x)

            results["classes"].append({
            "uri": c.c,
            "name": class_clean,
            "label": c.label,
            "comment": c.comment
        })

    for prop in tqdm(properties, total=len(properties), desc=f"{namespace} properties", unit="prop"): 
        if prop.p in namespace:              
            ns, local = split_uri(prop.p)
            prop_clean = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', local)
            prop_clean = re.sub(r'[_\-]+', ' ', prop_clean)
            prop_clean = prop_clean.lower().strip()

            properties_clean[prop.p] = prop_clean
            properties_text[prop.p] = " ".join(str(x) for x in (prop_clean, prop.label, prop.comment) if x)

            results["properties"].append({
            "uri": prop.p,
            "name": prop_clean,
            "label": prop.label,
            "comment": prop.comment
        })

    with open(CURRENT_FOLDER / "data" / "resources" / results_output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return classes_clean, properties_clean, classes_text, properties_text



cdm_classes, cdm_properties, cdm_classes_text, cdm_properties_text = prep_resources(onto_file=CDM_RDF, format="xml", namespace=CDM, results_output_file="cdm_ressources.json")
eli_classes, eli_properties, eli_classes_text, eli_properties_text = prep_resources(onto_file=ELI_OWL, format="xml", namespace=ELI, results_output_file="eli_ressources.json")