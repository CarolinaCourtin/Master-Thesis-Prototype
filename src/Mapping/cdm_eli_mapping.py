import json
from pathlib import Path
import requests
from rdflib import Graph
from SPARQLWrapper import SPARQLWrapper, JSON

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EUR_LEX_DATA_DIR = PROJECT_ROOT / "data" / "EUR_Lex"
# FEDLEX_ONTOLOGY_DEF = FEDLEX_DATA_DIR / "rdf" / "jolux-ontology-owl" / "jolux.ttl"

cdm_classes = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>

SELECT DISTINCT ?c
FROM <http://example.org/graph/europe>
WHERE { ?s a ?c }
"""


cdm_properties = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>

SELECT DISTINCT ?p 
FROM <http://example.org/graph/europe>
WHERE { ?s ?p ?o }
"""