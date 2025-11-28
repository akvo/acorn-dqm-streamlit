#!/usr/bin/env python3
"""
Species Classifier Script

Analyzes tree names from Unknown Species spreadsheet, classifies them as scientific
names using Claude AI, and fuzzy matches against a Species Registry.

Usage:
    python species_classifier.py --api-key YOUR_API_KEY [--threshold 90]
"""

import argparse
import re
import sys
import time
from typing import Tuple, Optional, Dict, List

import pandas as pd
from anthropic import Anthropic
from rapidfuzz import fuzz, process


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Classify tree names and match against species registry"
    )
    parser.add_argument(
        "--api-key",
        required=True,
        help="Anthropic API key for Claude"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=90,
        help="Fuzzy match threshold percentage (default: 90)"
    )
    parser.add_argument(
        "--input-unknown",
        default="Species_list_unknown.xlsx",
        help="Input file with unknown species (default: Species_list_unknown.xlsx)"
    )
    parser.add_argument(
        "--input-registry",
        default="Species_registry.xlsx",
        help="Input file with species registry (default: Species_registry.xlsx)"
    )
    parser.add_argument(
        "--output",
        default="Unknown_Species_Analyzed.xlsx",
        help="Output file name (default: Unknown_Species_Analyzed.xlsx)"
    )
    return parser.parse_args()


def load_unknown_species(filepath: str) -> pd.DataFrame:
    """Load the Unknown Species sheet from the spreadsheet."""
    print(f"Loading unknown species from {filepath}...", flush=True)
    df = pd.read_excel(filepath, sheet_name="Unknown Species")
    print(f"  Loaded {len(df)} rows", flush=True)
    return df


def load_species_registry(filepath: str) -> List[str]:
    """Load scientific names from the species registry."""
    print(f"Loading species registry from {filepath}...")
    df = pd.read_excel(filepath)
    # Filter out non-identifiable entries
    names = df["Scientific Name"].dropna().tolist()
    names = [n for n in names if n != "Name could not be identified"]
    print(f"  Loaded {len(names)} valid scientific names")
    return names


def extract_tree_name(issue_description: str) -> Optional[str]:
    """Extract tree name from Issue Description column."""
    if pd.isna(issue_description):
        return None
    match = re.search(r"Tree:\s*([^|]+)", str(issue_description))
    if match:
        return match.group(1).strip()
    return None


def classify_names_batch(
    tree_names: List[str],
    client: Anthropic,
    batch_size: int = 20
) -> Dict[str, Tuple[bool, str, str]]:
    """
    Use Claude Haiku to classify tree names in batches.
    Returns dict mapping name -> (identified, id_type, reasoning)
    """
    import json

    all_results = {}

    # Process in batches
    for i in range(0, len(tree_names), batch_size):
        batch = tree_names[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(tree_names) + batch_size - 1) // batch_size

        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} names)...", flush=True)

        names_json = json.dumps(batch)

        prompt = f"""Classify each plant/tree name into one of these types:
- "Species" = full scientific binomial (Genus species), e.g. "Quercus alba"
- "Genus" = genus name only or with "sp.", e.g. "Quercus", "Quercus sp."
- "Common" = recognized common/vernacular name, e.g. "Oak", "Lemon grass"
- "Unknown" = placeholders like "#Unknown", "Unknown 1", gibberish, or unidentifiable

Names: {names_json}

Return ONLY a JSON array with ALL {len(batch)} names:
[{{"name":"exact name from input","identified":true,"type":"Species","reasoning":"short reason"}}]

identified=true for Species/Genus/Common, false for Unknown."""

        for attempt in range(3):  # Retry up to 3 times
            try:
                response = client.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}]
                )

                response_text = response.content[0].text

                # Clean up response
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0]
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0]

                results = json.loads(response_text.strip())

                for item in results:
                    name = item.get("name", "")
                    identified = item.get("identified", False)
                    id_type = item.get("type", "Unknown") if identified else ""
                    reasoning = item.get("reasoning", "")
                    all_results[name] = (identified, id_type, reasoning)

                print(f"    -> Classified {len(results)} names", flush=True)
                break  # Success, exit retry loop

            except json.JSONDecodeError as e:
                if attempt < 2:
                    print(f"    -> Retry {attempt + 1}/3 (JSON parse error)", flush=True)
                    time.sleep(1)
                else:
                    print(f"    -> Failed after 3 attempts, raw response: {response_text[:200]}", flush=True)
            except Exception as e:
                if attempt < 2:
                    print(f"    -> Retry {attempt + 1}/3 due to: {e}", flush=True)
                    time.sleep(1)
                else:
                    print(f"    -> Failed after 3 attempts: {e}", flush=True)

    print(f"  Total classified: {len(all_results)}/{len(tree_names)}", flush=True)
    return all_results


def deduplicate_similar_names(names_df: pd.DataFrame, threshold: int = 90) -> pd.DataFrame:
    """
    Deduplicate similar species names using fuzzy matching.
    Returns DataFrame with unique names and a 'Variants' column showing consolidated names.
    """
    if names_df.empty:
        names_df["Variants"] = ""
        return names_df

    names = names_df["Tree Name"].tolist()

    # Group similar names
    groups = []  # List of lists of similar names
    used = set()

    for i, name1 in enumerate(names):
        if name1 in used:
            continue
        group = [name1]
        for j, name2 in enumerate(names[i+1:], i+1):
            if name2 in used:
                continue
            # Normalize for comparison
            n1 = name1.lower().strip().rstrip('.')
            n2 = name2.lower().strip().rstrip('.')
            if fuzz.ratio(n1, n2) >= threshold:
                group.append(name2)
                used.add(name2)
        used.add(name1)
        groups.append(group)

    # For each group, pick the "canonical" name (longest, prefer with period)
    result_rows = []
    for group in groups:
        # Sort by: has period at end, then by length (descending)
        canonical = max(group, key=lambda x: (x.rstrip().endswith('.'), len(x)))
        variants = [n for n in group if n != canonical]

        # Get the row data for canonical name
        row = names_df[names_df["Tree Name"] == canonical].iloc[0].to_dict()
        row["Variants"] = ", ".join(sorted(variants)) if variants else ""
        result_rows.append(row)

    result_df = pd.DataFrame(result_rows)
    # Reorder columns to put Variants at the end
    cols = [c for c in result_df.columns if c != "Variants"] + ["Variants"]
    return result_df[cols].sort_values("Tree Name").reset_index(drop=True)


def fuzzy_match(
    tree_name: str,
    registry_names: List[str],
    threshold: int
) -> Tuple[Optional[str], Optional[float]]:
    """
    Find the best fuzzy match for a tree name in the registry.

    Returns:
        Tuple of (matched_name, score) or (None, None) if no match above threshold
    """
    if not tree_name or not registry_names:
        return None, None

    # Normalize the tree name for comparison
    normalized_name = tree_name.strip().lower()

    # Use rapidfuzz to find best match
    result = process.extractOne(
        normalized_name,
        [n.lower() for n in registry_names],
        scorer=fuzz.ratio
    )

    if result and result[1] >= threshold:
        # Find the original (non-lowercased) name
        matched_idx = [n.lower() for n in registry_names].index(result[0])
        return registry_names[matched_idx], result[1]

    return None, None


def process_tree_names(
    df: pd.DataFrame,
    registry_names: List[str],
    client: Anthropic,
    threshold: int
) -> pd.DataFrame:
    """
    Process all tree names: extract, classify, and match.
    """
    # Extract tree names
    print("\nExtracting tree names...")
    df["Tree Name"] = df["Issue Description"].apply(extract_tree_name)

    # Get unique tree names for classification (to minimize API calls)
    unique_names = df["Tree Name"].dropna().unique().tolist()
    print(f"Found {len(unique_names)} unique tree names to classify")

    # Classify all names in batches
    print("\nClassifying names with Claude Haiku (batch)...", flush=True)
    classification_cache = classify_names_batch(unique_names, client)

    # Apply classifications to dataframe
    print("\nApplying classifications...", flush=True)

    def get_identified(name):
        if not name or name not in classification_cache:
            return "N"
        return "Y" if classification_cache[name][0] else "N"

    def get_id_type(name):
        if not name or name not in classification_cache:
            return ""
        return classification_cache[name][1] if classification_cache[name][0] else ""

    def get_reasoning(name):
        if not name or name not in classification_cache:
            return ""
        return classification_cache[name][2]

    df["Identified"] = df["Tree Name"].apply(get_identified)
    df["Identification Type"] = df["Tree Name"].apply(get_id_type)
    df["AI Reasoning"] = df["Tree Name"].apply(get_reasoning)

    # Fuzzy match identified names against registry
    print("\nPerforming fuzzy matching...", flush=True)
    match_cache: Dict[str, Tuple[Optional[str], Optional[float]]] = {}

    identified_names = [n for n in unique_names if classification_cache.get(n, (False, "", ""))[0]]
    print(f"  {len(identified_names)} identified names to match against registry", flush=True)

    for name in identified_names:
        if name not in match_cache:
            match_cache[name] = fuzzy_match(name, registry_names, threshold)

    # Apply matches to dataframe
    def get_match_status(row):
        name = row["Tree Name"]
        if not name or row["Identified"] == "N":
            return "N/A"
        match_result = match_cache.get(name, (None, None))
        return "Y" if match_result[0] else "N"

    def get_matched_name(row):
        name = row["Tree Name"]
        if not name or row["Identified"] == "N":
            return ""
        match_result = match_cache.get(name, (None, None))
        return match_result[0] if match_result[0] else ""

    def get_match_score(row):
        name = row["Tree Name"]
        if not name or row["Identified"] == "N":
            return ""
        match_result = match_cache.get(name, (None, None))
        return f"{match_result[1]:.1f}%" if match_result[1] else ""

    df["Matched in Registry"] = df.apply(get_match_status, axis=1)
    df["Registry Match"] = df.apply(get_matched_name, axis=1)
    df["Match Score"] = df.apply(get_match_score, axis=1)

    return df


def print_summary(df: pd.DataFrame):
    """Print summary statistics."""
    print("\n" + "=" * 50)
    print("SUMMARY STATISTICS")
    print("=" * 50)

    total = len(df)
    valid_names = df["Tree Name"].notna().sum()
    identified_yes = (df["Identified"] == "Y").sum()
    identified_no = (df["Identified"] == "N").sum()

    # Count by identification type
    id_types = df[df["Identified"] == "Y"]["Identification Type"].value_counts()

    matched_yes = (df["Matched in Registry"] == "Y").sum()
    matched_no = (df["Matched in Registry"] == "N").sum()

    print(f"Total rows processed:        {total}")
    print(f"Valid tree names extracted:  {valid_names}")
    print(f"Identified (Y):              {identified_yes}")
    print(f"Not identified (N):          {identified_no}")
    print(f"\nBy Identification Type:")
    for id_type, count in id_types.items():
        print(f"  - {id_type}: {count}")
    print(f"\nMatched in registry (Y):     {matched_yes}")
    print(f"Not matched in registry (N): {matched_no}")
    print("=" * 50)


def main():
    args = parse_args()

    # Validate API key
    print("Initializing Claude client...")
    client = Anthropic(api_key=args.api_key)

    # Test API connection
    try:
        client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=10,
            messages=[{"role": "user", "content": "test"}]
        )
        print("  API connection successful", flush=True)
    except Exception as e:
        print(f"Error: Failed to connect to Claude API: {e}")
        sys.exit(1)

    # Load data
    df = load_unknown_species(args.input_unknown)
    registry_names = load_species_registry(args.input_registry)

    # Process tree names
    df = process_tree_names(df, registry_names, client, args.threshold)

    # Reorder columns to put new columns after Issue Description
    original_cols = ["Submitted Date", "Plot ID", "Subplot ID", "Data Collector Name",
                     "Issue Type", "Issue Description", "Notes", "Clarification"]
    new_cols = ["Tree Name", "Identified", "Identification Type", "AI Reasoning",
                "Matched in Registry", "Registry Match", "Match Score"]

    # Keep only columns that exist
    final_cols = [c for c in original_cols if c in df.columns] + new_cols
    df = df[final_cols]

    # Create "Additional Unique Species" sheet - Identified=Y and Matched in Registry=N
    additional_species = df[
        (df["Identified"] == "Y") & (df["Matched in Registry"] == "N")
    ][["Tree Name", "Identification Type", "AI Reasoning"]].drop_duplicates(subset=["Tree Name"])
    additional_species = additional_species.sort_values("Tree Name").reset_index(drop=True)

    # Save output with multiple sheets
    print(f"\nSaving results to {args.output}...", flush=True)
    with pd.ExcelWriter(args.output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Unknown Species")
        additional_species.to_excel(writer, index=False, sheet_name="Additional Unique Species")
    print(f"  Sheet 1 'Unknown Species': {len(df)} rows", flush=True)
    print(f"  Sheet 2 'Additional Unique Species': {len(additional_species)} unique names", flush=True)

    # Print summary
    print_summary(df)

    print(f"\nDone! Results saved to {args.output}")


if __name__ == "__main__":
    main()
