from pathlib import Path
import json

CURRENT_FOLDER = Path(__file__).resolve().parents[0]
RESOURCES_FOLDER = CURRENT_FOLDER / "data" / "resources"
SCORES_FOLDER = CURRENT_FOLDER / "data" / "mapping_scores"
FILTERED_SCORES_FOLDER = CURRENT_FOLDER / "data" / "filtered_scores"


def load_eli_details():
    """
    Reads eli_ressources.json and returns a dict
    with all ELI details for both classes and properties.
    """

    with open(RESOURCES_FOLDER / "eli_ressources.json", encoding="utf-8") as f:
        data = json.load(f)

    details = {}

    for entry in data["classes"]:
        details[entry["uri"]] = {
            "name": entry["name"],
            "label": entry["label"],
            "comment": entry["comment"],
        }

    for entry in data["properties"]:
        details[entry["uri"]] = {
            "name": entry["name"],
            "label": entry["label"],
            "comment": entry["comment"],
        }

    return details


# Loaded once, used by every call below
ELI_DETAILS = load_eli_details()


def filter_mapping_file(input_file, output_file, limit, cutoff):
    """
    Reads a full mapping scores file (all pairs), keeps for each element only the
    candidates with score >= cutoff, at most limit of them, adds the ELI name,
    label and comment of each kept candidate, and saves the result in the same
    JSON format.
    """

    with open(SCORES_FOLDER / input_file, encoding="utf-8") as f:
        results = json.load(f)

    filtered_results = []

    for entry in results:

        kept_candidates = []

        for candidate in entry["candidates"]:

            if limit is not None and len(kept_candidates) >= limit:
                break

            if cutoff is not None and candidate["score"] < cutoff:
                continue

            new_candidate = dict(candidate)

            # Look up the ELI details of this candidate by its URI
            eli_info = ELI_DETAILS.get(candidate["candidate_uri"])
            if eli_info is not None:
                new_candidate["candidate_name"] = eli_info["name"]
                new_candidate["candidate_label"] = eli_info["label"]
                new_candidate["candidate_comment"] = eli_info["comment"]

            kept_candidates.append(new_candidate)

        new_entry = dict(entry)
        new_entry["candidates"] = kept_candidates

        filtered_results.append(new_entry)

    FILTERED_SCORES_FOLDER.mkdir(parents=True, exist_ok=True)

    with open(FILTERED_SCORES_FOLDER / output_file, "w", encoding="utf-8") as f:
        json.dump(filtered_results, f, indent=2, ensure_ascii=False)

    return filtered_results


filter_mapping_file("jolux_eli_classes_token_set_matching_results.json","jolux_eli_classes_fuzzy_top3_c70.json",limit=3, cutoff=70)

filter_mapping_file("jolux_eli_properties_embedding_matching_results.json","jolux_eli_properties_embedding_top3_c45.json",limit=3, cutoff=45)