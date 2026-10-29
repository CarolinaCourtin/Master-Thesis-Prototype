###  Folder structure for Fedlex 

```
data/Fedlex/
├── raw/
│   ├── fedlex_laws.json              # selected laws (input, written by hand)
│   ├── fedlex_consolidations.json    # consolidations of each law (generated)
│   └── xml/                          # French XML version of each law + download_log.json
└── rdf/
    ├── fedlex_base_data.ttl                 # RDF data retrieved from Fedlex
    └── fedlex_data_enriched_articles.ttl    # base data + articles added from the XML
```

The `rdf` files of each data soruce also contains the full definition of the used ont0ologies (respectively Jolux and CDM), as we can find them in the base web source. 