from pathlib import Path
from rdflib import Graph, Namespace
from rdflib.namespace import split_uri
import re
import json
from rapidfuzz import process, fuzz

import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

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

nltk.download('stopwords')
stemmer = PorterStemmer()
stop_words = set(stopwords.words('english'))

def tokenise(text):

    tokens = re.findall(r"[a-z0-9]+", text.lower())                 # lowercase + split, drops punctuation
    tokens = [t for t in tokens if t not in stop_words]             # remove stop words
    tokens = [stemmer.stem(t) for t in tokens]                      # stemming
    return " ".join(tokens)  


def prep_resources(onto_file, format, namespace, results_output_file):

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
    for c in classes:  
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

    for prop in properties:  
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

    with open(CURRENT_FOLDER / results_output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return classes_clean, properties_clean, classes_text, properties_text


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


def tf_idf_mapping(vocab_1, vocab_2, results_file, limit, cutoff):

    uris_1, texts_1 = list(vocab_1.keys()), list(vocab_1.values())
    uris_2, texts_2 = list(vocab_2.keys()), list(vocab_2.values())

    corpus_1 = [tokenise(t) for t in texts_1]
    corpus_2 = [tokenise(t) for t in texts_2]

    # one vectorizer, fitted on BOTH ontologies, same vocabulary and same IDF
    tfidf_vectorizer = TfidfVectorizer()
    tfidf_vectorizer.fit(corpus_1 + corpus_2)
    matrix_1 = tfidf_vectorizer.transform(corpus_1)
    matrix_2 = tfidf_vectorizer.transform(corpus_2)


    sim_tfidf = cosine_similarity(matrix_1, matrix_2)

    results = []
    for i, uri in enumerate(uris_1):
        top_tfidf = sim_tfidf[i].argsort()[::-1][:limit]      # best first
        results.append({
            "uri": uri,
            "text": texts_1[i],
            "candidates": [{"candidate_uri": uris_2[j],
                            "candidate_text": texts_2[j],
                            "score": round(float(sim_tfidf[i, j]) * 100, 1)}
                           for j in top_tfidf if sim_tfidf[i, j] * 100 >= cutoff],
        })

    with open(CURRENT_FOLDER / results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return results


cdm_classes, cdm_properties, cdm_classes_text, cdm_properties_text = prep_resources(onto_file=CDM_RDF, format="xml", namespace=CDM, results_output_file="cdm_ressources.json")
eli_classes, eli_properties, eli_classes_text, eli_properties_text = prep_resources(onto_file=ELI_OWL, format="xml", namespace=ELI, results_output_file="eli_ressources.json")

# fuzzy_mapping(eli_classes, cdm_classes, "eli_cdm_classes_token_set_matching_results.json", method=fuzz.token_set_ratio, limit=10, cutoff=60)
# fuzzy_mapping(eli_properties, cdm_properties, "eli_cdm_properties_token_set_matching_results.json", method=fuzz.token_set_ratio, limit=10, cutoff=60)

tf_idf_mapping(eli_classes_text, cdm_classes_text, results_file="eli_cdm_classes_tfidf_matching_results.json", limit=10, cutoff=5)
tf_idf_mapping(eli_properties_text, cdm_properties_text, results_file="eli_cdm_properties_tfidf_matching_results.json", limit=10, cutoff=5)