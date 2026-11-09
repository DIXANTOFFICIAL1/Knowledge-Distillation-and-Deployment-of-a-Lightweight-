#!/usr/bin/env python3
"""
Data Cleaning and Validation Pipeline for Distillation Dataset.
Reads all shard outputs from datasets/teacher/, applies strict validation rules (a)-(e),
generates sorted datasets/v1/train.jsonl and its SHA-256 checksum in datasets/v1/train.sha256.
"""

import os
import glob
import json
import hashlib
import sys

VALID_INTENTS = {
    "alarm_set",
    "alarm_query",
    "calendar_set",
    "calendar_query",
    "calendar_remove",
    "weather_query",
    "datetime_query",
    "recommendation_events"
}

REQUIRED_KEYS = {"intent", "date", "time", "place"}

def compute_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def clean_data(shard_pattern="datasets/teacher/shard-*.jsonl",
               out_path="datasets/v1/train.jsonl",
               checksum_path="datasets/v1/train.sha256"):
    
    shard_files = sorted(glob.glob(shard_pattern))
    if not shard_files:
        print(f"Warning: No shard files found matching {shard_pattern}")
        # Look for existing train.jsonl or fallback
        if os.path.exists(out_path):
            print(f"Existing {out_path} found. Recalculating checksum.")
            sha = compute_sha256(out_path)
            with open(checksum_path, "w", encoding="utf-8") as f_sha:
                f_sha.write(sha + "\n")
            print(f"SHA-256: {sha}")
            return

    raw_records = []
    for sf in shard_files:
        with open(sf, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    raw_records.append(json.loads(line))

    total_input = len(raw_records)
    count_a = 0  # Invalid JSON
    count_b = 0  # Invalid keys
    count_c = 0  # Invalid intent
    count_d = 0  # Slot hallucination / not substring
    count_e = 0  # Duplicates

    # Step 1: Filter individual replies against rules (a) to (d)
    valid_candidates = []
    for r in raw_records:
        cmd_id = r["id"]
        cmd_text = r["text"]
        raw_reply = r.get("teacher_raw", "")

        # (a) Check JSON validity
        try:
            if isinstance(raw_reply, dict):
                parsed = raw_reply
            else:
                # Strip code fences if present
                clean_str = raw_reply.strip()
                if clean_str.startswith("```"):
                    clean_str = clean_str.strip("`")
                    if clean_str.startswith("json"):
                        clean_str = clean_str[4:].strip()
                parsed = json.loads(clean_str)
        except Exception:
            count_a += 1
            continue

        if not isinstance(parsed, dict):
            count_a += 1
            continue

        # (b) Keys must be exactly intent, date, time, and place
        if set(parsed.keys()) != REQUIRED_KEYS:
            count_b += 1
            continue

        # (c) Intent must be one of the eight valid intents
        intent = parsed.get("intent")
        if intent not in VALID_INTENTS:
            count_c += 1
            continue

        # (d) Slot values must be null or text that appears in command
        slot_invalid = False
        text_lower = cmd_text.lower()
        for slot in ["date", "time", "place"]:
            val = parsed.get(slot)
            if val is not None:
                if not isinstance(val, str):
                    slot_invalid = True
                    break
                val_norm = val.strip().lower()
                if val_norm not in text_lower:
                    slot_invalid = True
                    break

        if slot_invalid:
            count_d += 1
            continue

        valid_candidates.append({
            "id": cmd_id,
            "text": cmd_text,
            "target": parsed
        })

    # (e) Duplicate commands (keep the one with the smallest id)
    # Sort candidates by id first so smallest id comes first
    valid_candidates.sort(key=lambda x: x["id"])
    seen_texts = {}
    deduped = []
    for item in valid_candidates:
        t = item["text"].strip().lower()
        if t in seen_texts:
            count_e += 1
        else:
            seen_texts[t] = item["id"]
            deduped.append(item)

    kept_count = len(deduped)

    # Write cleaned dataset
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f_out:
        for item in deduped:
            record_to_write = {
                "id": item["id"],
                "text": item["text"],
                "intent": item["target"]["intent"],
                "date": item["target"]["date"],
                "time": item["target"]["time"],
                "place": item["target"]["place"]
            }
            f_out.write(json.dumps(record_to_write) + "\n")

    # Generate SHA-256 checksum
    sha256_hash = compute_sha256(out_path)
    os.makedirs(os.path.dirname(checksum_path), exist_ok=True)
    with open(checksum_path, "w", encoding="utf-8") as f_sha:
        f_sha.write(sha256_hash + "\n")

    print("\n" + "=" * 50)
    print("DATASET CLEANING SUMMARY TABLE")
    print("=" * 50)
    print(f"Input records:               {total_input}")
    print(f"Rejected (a) [Invalid JSON]: {count_a}")
    print(f"Rejected (b) [Invalid Keys]: {count_b}")
    print(f"Rejected (c) [Bad Intent]:   {count_c}")
    print(f"Rejected (d) [Slot Substr]:  {count_d}")
    print(f"Duplicate commands (e):      {count_e}")
    print(f"Records kept:                {kept_count}")
    print(f"Sum check: {count_a + count_b + count_c + count_d + count_e + kept_count} == {total_input}")
    print(f"Output saved to: {out_path}")
    print(f"SHA-256 Checksum: {sha256_hash}")
    print("=" * 50 + "\n")

if __name__ == "__main__":
    clean_data()
