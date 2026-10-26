# Data preparation

This part of the project is dedicated to the retrieval and preparation of the legal data used in this study. It covers two sources :

1. **Fedlex**, the publication platform of Swiss federal law 
2. **EUR-Lex / Cellar**, the publication platform of European Union law

---

## Part 1 — Fedlex 

The `Fedlex` folder contains the scripts used to retrieve, from the Fedlex knowledge graph, the RDF data describing the set of laws included in this study. The resulting RDF data are stored in `data/Fedlex/`.

### Selection of the laws

The laws were selected by hand, based on their relevance to the digital law domain (data protection, information security and cybersecurity, electronic signatures and e-government, telecommunications, unfair competition, copyright, and the cyber-offences of the Criminal Code). The selection is stored in `data/Fedlex/raw/fedlex_laws.json`, which gives for each law its name, its number in the Classified Compilation, and its two Fedlex identifiers :

- **OC** (*Official Compilation*, `eli/oc/...`) : the act as originally published
- **CC** (*Classified Compilation*, `eli/cc/...`) : the abstract, consolidated law, to which its successive consolidated versions are attached

| Key | Law | SR |
|---|---|---|
| `nlpd` | Loi fédérale sur la protection des données (nLPD) | 235.1 |
| `opdo` | Ordonnance sur la protection des données (OPDo) | 235.11 |
| `ocpd` | Ordonnance sur les certifications en matière de protection des données (OCPD) | 235.13 |
| `lsi` | Loi sur la sécurité de l'information (LSI) | 128 |
| `ocys` | Ordonnance sur la cybersécurité (OCyS) | 128.51 |
| `conv_budapest` | Convention sur la cybercriminalité (Budapest) | 0.311.43 |
| `scse` | Loi sur la signature électronique (SCSE) | 943.03 |
| `lmeta` | Loi sur l'utilisation des moyens électroniques pour l'exécution des tâches des autorités (LMETA) | 172.019 |
| `ltc` | Loi sur les télécommunications (LTC) | 784.10 |
| `lscpt` | Loi sur la surveillance de la correspondance par poste et télécommunication (LSCPT) | 780.1 |
| `lcd` | Loi contre la concurrence déloyale (LCD) | 241 |
| `lda` | Loi sur le droit d'auteur (LDA) | 231.1 |
| `cp` | Code pénal suisse (CP) | 311.0 |


### Retrieval pipeline

#### Step 1 — Base laws and their metadata

For each law, both the CC and the OC URIs are dereferenced with an HTTP GET request asking for Turtle (`Accept: text/turtle`). Fedlex returns the RDF description of the resource, which is added to `fedlex_base_data.ttl`, available in the folder `data/Fedlex/rdf` . Since an RDF graph is a set of triples, retrieving the same resource twice does not create duplicates.

#### Step 2 — Consolidations

The consolidated versions of a law are not included in the description returned for the law itself. They are retrieved from the Fedlex SPARQL endpoint (`https://fedlex.data.admin.ch/sparqlendpoint`), where each consolidation is linked to its CC by the property `jolux:isMemberOf`. The consolidations of each law are listed in `fedlex_consolidations.json`, then dereferenced like the base laws and added to the same TTL file.

#### Step 3 — Completion of the articles (`fedlex_articles_enrich.py`)

The Fedlex knowledge graph does not always contain the complete set of articles composing a law. Since this study relies on article-level data, the missing articles are added from the French XML version of each law.

**Retrieval of the XML.** For each law, the script follows the structure of the Fedlex KG from the act (OC) to the file:

```
act (OC) --jolux:isRealizedBy--> expression (one per language)
         --jolux:isEmbodiedBy--> manifestation (one per format)
         --jolux:isExemplifiedBy--> file URL
```

and downloads the file whose URL corresponds to the French XML (`/fr/xml/`). Only the French version is retrieved, since the article list is the same in every language and the later steps of the study work on French texts. The outcome for each law is recorded in `data/Fedlex/raw/XML_Fedlex_laws`. When no XML version could be retrieved this way, a version available online was added to the XML folder by hand.

**Extraction of the articles.** The XML files follow the Akoma Ntoso standard, in which every article is an `<article>` element with an identifier (`eId`) such as `art_13`. Only top-level articles are kept:

- paragraphs, letters and other subdivisions *inside* an article are excluded (their `eId` contains a `/`, e.g. `art_32/para_2/lbl_a`);
- articles located in annexes are excluded (e.g. `annex_1/chap_6/art_25_a`): these are provisions of *other* laws amended by the act, not articles of the act itself.

**Addition to the graph.** Each missing article is added with the same structure as the articles already present in Fedlex, and linked to the CC of the law:

```turtle
<https://fedlex.data.admin.ch/eli/cc/2022/491/art_1>
    a jolux:LegalResourceSubdivision ;
    jolux:legalResourceSubdivisionIsPartOf <https://fedlex.data.admin.ch/eli/cc/2022/491> ;
    jolux:legalResourceSubdivisionType <https://fedlex.data.admin.ch/vocabulary/subdivision-type/art> .
```

The article URIs follow the Fedlex pattern (`<CC URI>/art_<number>`), so that the added articles are consistent with the existing ones and would match them if Fedlex completed its data later. Articles already present in Fedlex are not added again.

The result (base data and added articles) is saved in a separate file, `fedlex_data_enriched_articles.ttl`, so that the original Fedlex data and the enriched data are never mixed.

### Reproducing the data

Requirements: Python 3.8 with the packages listed in `requirements.txt`.

1. Write the selection of laws in `data/Fedlex/raw/fedlex_laws.json`.
2. Run the retrieval script to produce `fedlex_consolidations.json` and `fedlex_base_data.ttl`.
3. Run `fedlex_articles_enrich.py` to download the French XML versions and produce `fedlex_data_enriched_articles.ttl`.

When loading the data into GraphDB, the base data and the enriched data can be imported into separate named graphs, so that queries can target either the original Fedlex data or the completed data.

### Sources

- Fedlex, publication platform of Swiss federal law : https://www.fedlex.admin.ch
- Fedlex SPARQL endpoint : https://fedlex.data.admin.ch/sparqlendpoint
- JOLux ontology (used by Fedlex) : http://data.legilux.public.lu/resource/ontology/jolux#
- Akoma Ntoso (XML format of the laws) : http://docs.oasis-open.org/legaldocml/ns/akn/3.0