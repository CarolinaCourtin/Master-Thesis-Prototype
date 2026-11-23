from pathlib import Path
import re
import json
from tqdm import tqdm
from rapidfuzz import process, fuzz

import nltk
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from sentence_transformers import SentenceTransformer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CURRENT_FOLDER = Path(__file__).resolve().parents[0]

nltk.download('stopwords')
stemmer = PorterStemmer()
stop_words = set(stopwords.words('english'))

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2") 

def load_resources(json_file):
    with open(CURRENT_FOLDER / "data" / "resources" / json_file, encoding="utf-8") as f:
        data = json.load(f)

    def to_text(e):
        return " ".join(x for x in (e["name"], e["label"], e["comment"]) if x)

    class_names  = {e["uri"]: e["name"]  for e in data["classes"]}
    class_texts  = {e["uri"]: to_text(e) for e in data["classes"]}
    prop_names   = {e["uri"]: e["name"]  for e in data["properties"]}
    prop_texts   = {e["uri"]: to_text(e) for e in data["properties"]}

    return class_names, class_texts, prop_names, prop_texts

def tokenise(text):

    tokens = re.findall(r"[a-z0-9]+", text.lower())                 # lowercase + split, drops punctuation
    tokens = [t for t in tokens if t not in stop_words]             # remove stop words
    tokens = [stemmer.stem(t) for t in tokens]                      # stemming
    return " ".join(tokens)  



def fuzzy_mapping(vocab_1, vocab_2, results_file, method, limit, cutoff):

    """
    This function takes as an input two dictionnaires containing the 
    set of classes or properties from the two ontologies we want to 
    compare using fuzzy matching. The parameters of the fuzzy matching
    method can be changed using the functions input. 
    
    """

    results = []
    for uri, name in tqdm(vocab_1.items(), total=len(vocab_1), desc=f"Fuzzy {results_file}", unit="uri"): # eli : one by one 
        matches = process.extract(name, vocab_2,scorer=method,limit=limit, score_cutoff=cutoff)
        results.append({
            "uri": uri,
            "name": name,
            "candidates": [{"candidate_uri": cand_uri, "candidate_name": cand_name,"score": round(score, 1)}
                           for cand_name, score, cand_uri in matches],
        })


    with open(CURRENT_FOLDER / "data" / "mapping_scores" / results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def tf_idf_mapping(vocab_1, vocab_2, results_file, limit, cutoff):

    uris_1, texts_1 = list(vocab_1.keys()), list(vocab_1.values())
    uris_2, texts_2 = list(vocab_2.keys()), list(vocab_2.values())

    corpus_1 = [tokenise(t) for t in tqdm(texts_1, desc="Tokenising source", unit="txt")]
    corpus_2 = [tokenise(t) for t in tqdm(texts_2, desc="Tokenising target", unit="txt")]

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

    with open(CURRENT_FOLDER / "data" / "mapping_scores" / results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return results


def sentence_embedding_mapping(vocab_1, vocab_2, results_file, model, limit, cutoff):

    uris_1, texts_1 = list(vocab_1.keys()), list(vocab_1.values())
    uris_2, texts_2 = list(vocab_2.keys()), list(vocab_2.values())

    # One vector per text
    vectors_1 = model.encode(texts_1, normalize_embeddings=True, show_progress_bar=True) # normalizes_emneddings rescales each vector so its length is exactly 1
    vectors_2 = model.encode(texts_2, normalize_embeddings=True, show_progress_bar=True)

    sim_emb = cosine_similarity(vectors_1, vectors_2)

    results = []
    for i, uri in enumerate(uris_1):
        top_emb = sim_emb[i].argsort()[::-1][:limit] 
        results.append({
            "uri": uri,
            "text": texts_1[i],
            "candidates": [{"candidate_uri": uris_2[j],
                            "candidate_text": texts_2[j],
                            "score": round(float(sim_emb[i, j]) * 100, 1)}
                           for j in top_emb if sim_emb[i, j] * 100 >= cutoff],
        })

    with open(CURRENT_FOLDER / "data" / "mapping_scores" / results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return results



# Loading the CDM, JOLUX and ELI resources from the JSON files
eli_classes, eli_classes_text, eli_properties, eli_properties_text = load_resources("eli_ressources.json")
cdm_classes, cdm_classes_text, cdm_properties, cdm_properties_text = load_resources("cdm_ressources.json")
jolux_classes, jolux_classes_text, jolux_properties, jolux_properties_text = load_resources("jolux_missing_alignments.json")


# --- mapping score between CDM and ELI resources ---
fuzzy_mapping(cdm_classes, eli_classes, "eli_cdm_classes_token_set_matching_results.json", method=fuzz.token_set_ratio, limit=10, cutoff=60)
fuzzy_mapping(cdm_properties, eli_properties, "eli_cdm_properties_token_set_matching_results.json", method=fuzz.token_set_ratio, limit=10, cutoff=60)

tf_idf_mapping(cdm_classes_text, eli_classes_text, results_file="eli_cdm_classes_tfidf_matching_results.json", limit=10, cutoff=5)
tf_idf_mapping(cdm_properties_text, eli_properties_text, results_file="eli_cdm_properties_tfidf_matching_results.json", limit=10, cutoff=5)
 
sentence_embedding_mapping(cdm_classes_text, eli_classes_text,"eli_cdm_classes_embedding_matching_results.json", model=model, limit=10, cutoff=0)
sentence_embedding_mapping(cdm_properties_text, eli_properties_text,"eli_cdm_properties_embedding_matching_results.json", model=model, limit=10, cutoff=0)


# --- mapping scores between JOLUX and ELI resources ---
fuzzy_mapping(jolux_classes, eli_classes, "eli_jolux_classes_token_set_matching_results.json", method=fuzz.token_set_ratio, limit=10, cutoff=60)
fuzzy_mapping(jolux_properties, eli_properties, "eli_jolux_properties_token_set_matching_results.json", method=fuzz.token_set_ratio, limit=10, cutoff=60)

'''
tf_idf_mapping(eli_classes_text, jolux_classes_text, results_file="eli_jolux_classes_tfidf_matching_results.json", limit=10, cutoff=5)
tf_idf_mapping(eli_properties_text, jolux_properties_text, results_file="eli_jolux_properties_tfidf_matching_results.json", limit=10, cutoff=5)
 
sentence_embedding_mapping(eli_classes_text, jolux_classes_text,"eli_jolux_classes_embedding_matching_results.json", model=model, limit=10, cutoff=0)
sentence_embedding_mapping(eli_properties_text, jolux_properties_text,"eli_jolux_properties_embedding_matching_results.json", model=model, limit=10, cutoff=0)
'''