from pathlib import Path
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import split_uri
import re
import json
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CURRENT_FOLDER = Path(__file__).resolve().parents[0]

JOLUX_DATA_DIR = PROJECT_ROOT / "data" / "Fedlex"
JOLUX_TTL = JOLUX_DATA_DIR / "rdf" / "jolux-ontology-owl" / "jolux.ttl"


CDM = Namespace("http://publications.europa.eu/ontology/cdm#")
ELI = Namespace("http://data.europa.eu/eli/ontology#")
JOLUX = Namespace("http://data.legilux.public.lu/resource/ontology/jolux#")
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
OWL = Namespace("http://www.w3.org/2002/07/owl#")

QUERIES_DIR = CURRENT_FOLDER / "queries"


tqdm.write(f"Parsing {JOLUX_TTL.name}...")
g = Graph()
g.parse(JOLUX_TTL, format="turtle")


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

def list_mapped_classes():

    mapped_classes = set()
    class_equivalences = {}    
    
    mapped_subclasses_query = (QUERIES_DIR / "jolux_eli_subclasses.rq").read_text(encoding="utf-8")
    res_query1 = g.query(mapped_subclasses_query)

    for row in res_query1:
        mapped_classes.add(row["joluxClass"])
        class_equivalences.setdefault(row["joluxClass"], []).append(str(row["eliClasses"]))

    mapped_vocabs_query = (QUERIES_DIR / "jolux_vocabulary_classes.rq").read_text(encoding="utf-8")
    res_query2 = g.query(mapped_vocabs_query)

    for row in res_query2:
        mapped_classes.add(row["joluxClass"])
        class_equivalences.setdefault(row["joluxClass"], []).append(str(row["conceptScheme"]))

    mapped_comments_query = (QUERIES_DIR / "jolux_alignmentComment_classes.rq").read_text(encoding="utf-8")
    res_query3 = g.query(mapped_comments_query)

    for row in res_query3:
        subject = row["classes"]
        comment = str(row["alignmentComments"])

        if subject in JOLUX:
            mapped_classes.add(subject)
            class_equivalences.setdefault(subject, []).append(comment)

        # finds every "jolux:SomeName" written in the comment and retrieve the name only before converting it into the actual JOLUX URI
        names = re.findall(r"jolux:([A-Za-z][A-Za-z0-9_\-]*)", comment)

        for name in names:
            # rebuild URI
            uri = URIRef(JOLUX + name)

            # check if the class truly exists
            if (uri, RDF.type, OWL.Class) in g:
                mapped_classes.add(uri)
                class_equivalences.setdefault(uri, []).append(str(subject))

    return mapped_classes, class_equivalences

def list_mapped_properties():

    direct_mappings = set()
    manual_mappings = {}  
    commented_mappings = set()
    commented_non_mappings = set() # properties commented as no alignment 

    prop_equivalences = {}

    non_mappings_comments = ["pas d'alignement eli", "pas d'alignement sur eli", "Thomas: pas d'alignement ?", "Thomas: quel alignement ?", "pas d'équivalent eli"]

    mapped_props = set()
    not_a_property = set()

    # direct mappings
    direct_mapping_query = (QUERIES_DIR / "jolux_eli_subproperties.rq").read_text(encoding="utf-8")
    res_query_direct = g.query(direct_mapping_query)

    for row in res_query_direct:
        direct_mappings.add(row["joluxProp"])
        prop_equivalences.setdefault(row["joluxProp"], []).append(str(row["eliProps"]))



    # mappings through comments
    alignment_comments_query = (QUERIES_DIR / "jolux_alignment_properties.rq").read_text(encoding="utf-8")
    res_query_comments = g.query(alignment_comments_query)

    for row in res_query_comments:
        subject = row["property"]
        comment = str(row["alignmentComments"])

        if subject in ELI:
            names = re.findall(r"jolux:([A-Za-z][A-Za-z0-9_\-]*)", comment)

            for name in names:
                uri = URIRef(JOLUX + name)
                if (uri, RDF.type, OWL.ObjectProperty) in g or (uri, RDF.type, OWL.DatatypeProperty) in g:
                    commented_mappings.add(uri)
                    prop_equivalences.setdefault(uri, []).append(str(subject))
                else:
                    not_a_property.add(uri)


        # if the comments states directly that there is not mapping 
        if subject in JOLUX:

            is_non_mapping = False                     # reset for EVERY property
            for phrase in non_mappings_comments:
                if phrase.lower() in comment.lower():
                    is_non_mapping = True

            if is_non_mapping:
                commented_non_mappings.add(subject)
            else:
                manual_mappings[subject] = comment
                print(f"Manual mapping found for entity : {subject} : {comment}")

    # Each property ends up in ONE set only, by priority : direct > commented > commented as not aligned > manual
    # Some properties fall in multiple different case scenario by error 
    commented_mappings = commented_mappings - direct_mappings
    commented_non_mappings = commented_non_mappings - direct_mappings - commented_mappings

    for uri in list(manual_mappings):
        if uri in direct_mappings or uri in commented_mappings or uri in commented_non_mappings:
            del manual_mappings[uri]

    mapped_props = direct_mappings | commented_mappings

    return  mapped_props, commented_non_mappings, manual_mappings, prop_equivalences

def get_metadata(list_entities, desc="entities", equivalences=None):
    
    """ Gets the metadata (label and comment) of a list of entities (classes or properties) """

    entities_clean = {}
    entities_text = {}          # {uri: "name label comment"} for TF-IDF / embeddings
    entries = []

    for uri in tqdm(sorted(list_entities), desc=desc, unit="uri"):

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

            entities_clean[uri] = class_clean
            entities_text[uri] = " ".join(text_parts)

            entry = {"uri": str(uri), "name": class_clean, "label": label, "comment": comment}
            if equivalences is not None:
                entry["equivalence"] = equivalences.get(uri, [])
            entries.append(entry)

    return entries, entities_clean, entities_text

# --- classes ---
tqdm.write("Listing classes...")
mapped_classes, class_equivalences = list_mapped_classes()
all_classes = list_jolux_classes()
missing_classes = all_classes - mapped_classes

# --- properties ---
tqdm.write("Listing properties...")
mapped_properties, non_mapped_comments, manual_mappings, prop_equivalences = list_mapped_properties()
all_properties = list_jolux_props()
missing_properties = all_properties - mapped_properties - set(manual_mappings)   # includes non_mapped_comments

# --- metadata ---
mapped_classes_entries, mapped_classes_clean, mapped_classes_text = get_metadata(mapped_classes, desc="Mapped classes", equivalences=class_equivalences)
missing_classes_entries, missing_classes_clean, missing_classes_text = get_metadata(missing_classes, desc="Missing classes")
mapped_props_entries, mapped_props_clean, mapped_props_text = get_metadata(mapped_properties, desc="Mapped properties", equivalences=prop_equivalences)
missing_props_entries, missing_props_clean, missing_props_text = get_metadata(missing_properties, desc="Missing properties")
manual_props_entries, manual_props_clean, manual_props_text = get_metadata(manual_mappings, desc="Manual properties")


# saving in JSON files
with open(CURRENT_FOLDER / "data" / "resources" / "jolux_alignments_with_ELI.json", "w", encoding="utf-8") as f:
    json.dump({"classes": mapped_classes_entries, "properties": mapped_props_entries},
              f, indent=2, ensure_ascii=False)

with open(CURRENT_FOLDER / "data" / "resources" / "jolux_missing_alignments.json", "w", encoding="utf-8") as f:
    json.dump({"classes": missing_classes_entries, "properties": missing_props_entries},
              f, indent=2, ensure_ascii=False)

with open(CURRENT_FOLDER / "data" / "resources" / "jolux_manual_alignments.json", "w", encoding="utf-8") as f:
    json.dump({"properties": manual_props_entries}, f, indent=2, ensure_ascii=False)