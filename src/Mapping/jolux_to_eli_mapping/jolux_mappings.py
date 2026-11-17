from pathlib import Path
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import split_uri
import re
import json

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CURRENT_FOLDER = Path(__file__).resolve().parents[0]

JOLUX_DATA_DIR = PROJECT_ROOT / "data" / "Fedlex"
JOLUX_TTL = JOLUX_DATA_DIR / "rdf" / "jolux-ontology-owl" / "jolux.ttl"

ELI_DATA_DIR = PROJECT_ROOT / "data" / "ELI-release"
ELI_OWL = ELI_DATA_DIR / "eli.owl"


CDM = Namespace("http://publications.europa.eu/ontology/cdm#")
ELI = Namespace("http://data.europa.eu/eli/ontology#")
JOLUX = Namespace("http://data.legilux.public.lu/resource/ontology/jolux#")
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
OWL = Namespace("http://www.w3.org/2002/07/owl#")

QUERIES_DIR = CURRENT_FOLDER / "queries"


g = Graph()
g.parse(JOLUX_TTL, format="turtle") 



mapped_props = set ()
non_mapped_props = set()



def clean_name(uri):
    ns, local = split_uri(uri)
    name = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', local)
    name = re.sub(r'[_\-]+', ' ', name)
    return name.lower().strip()


def list_jolux_classes():

    all_jolux_classes = set()

    query = """
    PREFIX rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX owl:   <http://www.w3.org/2002/07/owl#>
    PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>

    SELECT ?classUri
    WHERE {
        ?classUri rdf:type owl:Class .
        FILTER STRSTARTS(STR(?classUri), STR(jolux:))
    }
    """

    res = g.query(query)

    for uri in res:
        all_jolux_classes.add(uri.classUri)

    return all_jolux_classes

def list_jolux_props():

    all_jolux_properties = set()

    query= """
    PREFIX rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs:  <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX owl:   <http://www.w3.org/2002/07/owl#>
    PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>

    SELECT ?prop
    WHERE {
        VALUES ?kind { owl:ObjectProperty owl:DatatypeProperty }
        ?prop rdf:type ?kind .
        FILTER STRSTARTS(STR(?prop), STR(jolux:))
    }

    """

    res = g.query(query)
    for uri in res:
        all_jolux_properties.add(uri.prop)

    return all_jolux_properties

def save_data(list_entities, output_file):

    classes_clean = {}
    classes_text = {}          # {uri: "name label comment"} for TF-IDF / embeddings

    results = {
        "classes" : [],
        "properties" : []
    }

    for uri in sorted(list_entities):

        jolux_uri_metadata = f"""
            PREFIX rdfs:  <http://www.w3.org/2000/01/rdf-schema#>

            SELECT (GROUP_CONCAT(DISTINCT STR(?label) ; separator=" | ") AS ?labels)
                   (GROUP_CONCAT(DISTINCT STR(?comment) ; separator=" | ") AS ?comments)
            WHERE {{
                OPTIONAL {{ <{uri}> rdfs:label ?label .     FILTER(LANG(?label) IN ("fr", "")) }}
                OPTIONAL {{ <{uri}> rdfs:comment ?comment . FILTER(LANG(?comment) IN ("fr", "")) }}
            }}
            """
        res = g.query(jolux_uri_metadata)

        for met in res:         

            label = str(met["labels"]) if met["labels"] else None # some classes have multiple labels and comments
            comment = str(met["comments"]) if met["comments"] else None

            class_clean = clean_name(uri)

            # text for TF-IDF + embeddings
            text_parts = [class_clean]
            if label:
                text_parts.append(label)
            if comment:
                text_parts.append(comment)

            classes_clean[uri] = class_clean
            classes_text[uri] = " ".join(text_parts)

            results["classes"].append({
                "uri": str(uri),
                "name": class_clean,
                "label": label,
                "comment": comment
            })

    with open(CURRENT_FOLDER / output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return classes_clean, classes_text

def list_mapped_classes():

    mapped_classes = set()
    
    mapped_subclasses_query = (QUERIES_DIR / "jolux_eli_subclasses.rq").read_text(encoding="utf-8")
    res_query1 = g.query(mapped_subclasses_query)

    for row in res_query1:
        mapped_classes.add(row["joluxClass"])

    mapped_vocabs_query = (QUERIES_DIR / "jolux_vocabulary_classes.rq").read_text(encoding="utf-8")
    res_query2 = g.query(mapped_vocabs_query)

    for row in res_query2:
        mapped_classes.add(row["joluxClass"])

    mapped_comments_query = (QUERIES_DIR / "jolux_alignmentComment_classes.rq").read_text(encoding="utf-8")
    res_query3 = g.query(mapped_comments_query)

    for row in res_query3:
        subject = row["classes"]
        comment = str(row["alignmentComments"])

        if subject in JOLUX:
            mapped_classes.add(subject)

        # finds every "jolux:SomeName" written in the comment and retrieve the name only before converting it into the actual JOLUX URI
        names = re.findall(r"jolux:([A-Za-z][A-Za-z0-9_\-]*)", comment)

        for name in names:
            # rebuild URI
            uri = URIRef(JOLUX + name)

            # check if the class truly exists
            if (uri, RDF.type, OWL.Class) in g:
                mapped_classes.add(uri)

    return mapped_classes

mapped_classes = list_mapped_classes()
all_classes = list_jolux_classes()
missing_classes = all_classes - mapped_classes

mapped_classes_clean, mapped_classes_text = save_data(list_entities=mapped_classes, output_file="jolux_alignments.json")
notmapped_classes_clean, notmapped_classes_text=save_data(missing_classes, "jolux_missing_alignments.json")