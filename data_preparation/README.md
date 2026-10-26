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

**Retrieval of the XML** : For each law, the script follows the structure of the Fedlex KG from the act (OC) to the file:

```
act (OC) --jolux:isRealizedBy--> expression (one per language)
         --jolux:isEmbodiedBy--> manifestation (one per format)
         --jolux:isExemplifiedBy--> file URL
```

and downloads the file whose URL corresponds to the French XML (`/fr/xml/`). Only the French version is retrieved, since the article list is the same in every language and the later steps of the study work on French texts. The outcome for each law is recorded in `data/Fedlex/raw/XML_Fedlex_laws`. When no XML version could be retrieved this way, a version available online was added to the XML folder by hand.

**Extraction of the articles** : The XML files follow the Akoma Ntoso standard, in which every article is an `<article>` element with an identifier (`eId`) such as `art_13`. Only top-level articles are kept:

- paragraphs, letters and other subdivisions *inside* an article are excluded (their `eId` contains a `/`, e.g. `art_32/para_2/lbl_a`);
- articles located in annexes are excluded (e.g. `annex_1/chap_6/art_25_a`): these are provisions of *other* laws amended by the act, not articles of the act itself.

**Addition to the graph** : Each missing article is added with the same structure as the articles already present in Fedlex, and linked to the CC of the law:

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

## Part 2 — EUR-Lex

The `EUR_Lex` folder contains the scripts used to retrieve, from the knowledge graph of the EU Publications Office (Cellar, the repository behind EUR-Lex), the RDF data describing the EU legal acts included in this study. The resulting data are stored in `data/EUR_Lex/`.

### Selection of the laws

The EU acts were selected by hand based on their relevance to the digital law domain. The set of laws were also chosen based on the swiss set by trying to find matches on whether they are regulating the same subject. The selection is stored in `data/EUR_Lex/raw/eurlex_laws.json`.

| Key | Act | CELEX | Swiss equivalent(s) |
|---|---|---|---|
| `rgpd` | Règlement (UE) 2016/679 (RGPD) | 32016R0679 | 
| `directive_police_justice` | Directive (UE) 2016/680 (protection des données en matière pénale) | 32016L0680 | 
| `reglement_protection_donnees_institutions_ue` | Règlement (UE) 2018/1725 (protection des données par les institutions de l'Union) | 32018R1725 |
| `reglement_cybersecurite_institutions_ue` | Règlement (UE, Euratom) 2023/2841 (cybersécurité des institutions de l'Union) | 32023R2841 | 
| `nis2` | Directive (UE) 2022/2555 (SRI 2 / NIS2) | 32022L2555 |
| `nis2_execution` | Règlement d'exécution (UE) 2024/2690 (modalités d'application de NIS2) | 32024R2690 | 
| `cybersecurity_act` | Règlement (UE) 2019/881 (règlement sur la cybersécurité) | 32019R0881 |
| `directive_attaques_systemes_information` | Directive 2013/40/UE (attaques contre les systèmes d'information) | 32013L0040 |
| `eidas` | Règlement (UE) n° 910/2014 (eIDAS) | 32014R0910 | 
| `eidas2` | Règlement (UE) 2024/1183 (identité numérique européenne) | 32024R1183 | 
| `europe_interoperable` | Règlement (UE) 2024/903 (Europe interopérable) | 32024R0903 | 
| `donnees_ouvertes` | Directive (UE) 2019/1024 (données ouvertes) | 32019L1024 |
| `code_communications_electroniques` | Directive (UE) 2018/1972 (code des communications électroniques européen) | 32018L1972 |
| `internet_ouvert` | Règlement (UE) 2015/2120 (internet ouvert) | 32015R2120 |
| `vie_privee_communications_electroniques` | Directive 2002/58/CE (vie privée et communications électroniques) | 32002L0058 |
| `preuves_electroniques` | Règlement (UE) 2023/1543 (preuves électroniques) | 32023R1543 | 
| `pratiques_commerciales_deloyales` | Directive 2005/29/CE (pratiques commerciales déloyales) | 32005L0029 |
| `commerce_electronique` | Directive 2000/31/CE (commerce électronique) | 32000L0031 |
| `droit_auteur_marche_unique_numerique` | Directive (UE) 2019/790 (droit d'auteur dans le marché unique numérique) | 32019L0790 |
| `societe_information_droit_auteur` | Directive 2001/29/CE (droit d'auteur dans la société de l'information) | 32001L0029 |
| `programmes_ordinateur` | Directive 2009/24/CE (programmes d'ordinateur) | 32009L0024 |
| `bases_de_donnees` | Directive 96/9/CE (bases de données) | 31996L0009 |

### Retrieval pipeline 

The script `eurlex_base_data_extraction.py` queries the Cellar SPARQL endpoint (`https://publications.europa.eu/webapi/rdf/sparql`) in three steps, each adding its triples to `eurlex_base_data.ttl`. 

The endpoint returns a limited number of rows per query, without warning when a result is cut off. All queries are therefore ordered (`ORDER BY`) and fetched page by page (`LIMIT` / `OFFSET`, 5,000 rows per page) until an incomplete page is returned.

#### Step 1 — Acts and their direct links

Using the first function `get_eurlex_base_resources()`, for each act, two queries retrieve every triple in which the act appears :

- **outgoing triples** (`<act> ?p ?o`): the act's own metadata (title, dates, CELEX, ELI, EuroVoc descriptors...) and its links to other resources;
- **incoming triples** (`?s ?p <act>`): the resources pointing to the act, such as acts citing or amending it, its expressions, and its consolidated versions.

The number of triples retrieved per act is recorded in `data/EUR_Lex/rdf/eurlex_base_data_log.json`.

#### Step 2 — Expressions, manifestations and items

Step 1 only retrieves the link from each expression to the act, not the expressions' own data, and none of the manifestations and items. Three queries per act retrieve all the triples of its expressions, of their manifestations, and of their items. By default all languages are retrieved (`language=None`) but the function can be restricted to one language, e.g. `language="FRA"`.
This step is done using the function `add_eurlex_expressions_manifestations_items()`.

#### Step 3 — Consolidations 

This step retrieved the consolidations of each acts linked by `act_consolidated_based_on_resource_legal`. They are found in the file produced by step 1, and for each of them four queries retrieve its metadata, its expressions, its manifestations and its items. This step is done using the dedicated function `add_eurlex_consolidations()`.

### Extraction of the articles

Unlike JOLux, the CDM ontology does not model the subdivisions of an act : Cellar contains no resource for the articles. The articles are therefore extracted from the text of each act additionally using the script `add_eurlex_articles.py`.

**Retrieveal of XML acts** : For each act, the script finds the French expression in `eurlex_base_data.ttl`, then its manifestations, and chooses the first available format in this order :

- `fmx4`: Formex 4, the XML format of the EU Publications Office
- `xhtml` and `html`: used for the oldest acts which have no Formex version.

The items of the chosen manifestation are downloaded into `data/EUR_Lex/raw/XML_Eurlex_laws`. A Formex manifestation is split into several items:  a metadata file (`.doc.xml`), the text of the act and, often, one file per annex. For recent acts, the Formex item is a single zip archive containing these files, which the script extracts. The outcome for each act is recorded in `articles_log.json`.

The requests are sent over HTTPS with browser-like headers, since the server can refuse requests from scripts with an HTTP 403 error.

**Extraction** : In Formex, each article is an `<ARTICLE>` element whose `IDENTIFIER` attribute gives its number (`001`, `005A`...). For the acts without Formex, the article titles ("Article premier", "Article 12"...) are read from the HTML.

**Addition to the graph** : Each article is described with the ELI ontology:

```turtle
<http://publications.europa.eu/resource/cellar/3e485e15-.../art_5>
    a eli:LegalResourceSubdivision ;
    eli:is_part_of <http://publications.europa.eu/resource/cellar/3e485e15-...> ;
    eli:type_subdivision <http://publications.europa.eu/resource/authority/subdivision/ART> ;
    eli:number "5" .
```

- `eli:LegalResourceSubdivision`, `eli:is_part_of` and `eli:type_subdivision` are defined by the ELI ontology.
- The ELI ontology does not define the values of `eli:type_subdivision` and refers to the subdivision table of the EU Publications Office; the "article" concept of this table is used, and described in the graph as a `skos:Concept` of type `eli:SubdivisionType`.
- Since Cellar has no article identifiers, the article URIs are minted for this study, following the pattern used for Fedlex (`<act URI>/art_<number>`). They are not official EUR-Lex identifiers.

The result (base data + added articles) is saved in a separate file, `eurlex_data_enriched_articles.ttl`.

### Sources

- Fedlex, publication platform of Swiss federal law : https://www.fedlex.admin.ch
- Fedlex SPARQL endpoint : https://fedlex.data.admin.ch/sparqlendpoint
- JOLux ontology (used by Fedlex) : http://data.legilux.public.lu/resource/ontology/jolux#
- Akoma Ntoso (XML format of the laws) : http://docs.oasis-open.org/legaldocml/ns/akn/3.0
- EUR-Lex: https://eur-lex.europa.eu
- Cellar SPARQL endpoint: https://publications.europa.eu/webapi/rdf/sparql
- CDM ontology: http://publications.europa.eu/ontology/cdm#
- ELI ontology: http://data.europa.eu/eli/ontology#
- EU Vocabularies (authority tables, including the subdivision table): https://op.europa.eu/en/web/eu-vocabularies
- Formex (XML format of the Official Journal): https://op.europa.eu/en/web/eu-vocabularies/formex