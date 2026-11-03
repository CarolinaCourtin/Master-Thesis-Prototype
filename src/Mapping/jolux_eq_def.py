import json
from pathlib import Path
import requests
from rdflib import Graph
from SPARQLWrapper import SPARQLWrapper, JSON

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEDLEX_DATA_DIR = PROJECT_ROOT / "data" / "Fedlex"
FEDLEX_ONTOLOGY_DEF = FEDLEX_DATA_DIR / "rdf" / "jolux-ontology-owl" / "jolux.ttl"

