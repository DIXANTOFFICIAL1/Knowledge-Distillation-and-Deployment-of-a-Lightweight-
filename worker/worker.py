#!/usr/bin/env python3
"""
Sharded Ollama Teacher Labelling Worker.
Reads SHARD_INDEX and SHARD_COUNT, partitions commands from commands_pool.jsonl,
queries phi3.5 via Ollama, and outputs raw replies to shard JSONL.
"""

import os
import sys
import json
import urllib.request
import urllib.error
import boto3

def get_env_var(name, default=None, required=True):
    val = os.environ.get(name, default)
    if required and val is None:
        sys.exit(f"Error: Missing required environment variable {name}")
    return val

def load_prompt(prompt_path):
    if not os.path.exists(prompt_path):
        sys.exit(f"Error: Teacher prompt not found at {prompt_path}")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read().strip()

def query_ollama(ollama_url, model, prompt, text):
    full_prompt = f"{prompt}\n\nCommand: {text}\nJSON:"
    payload = {
        "model": model,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "seed": 42
        }
    }
    req = urllib.request.Request(
        f"{ollama_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "").strip()
    except Exception as e:
        print(f"Error querying Ollama: {e}", file=sys.stderr)
        return ""

def main():
    shard_index = int(get_env_var("SHARD_INDEX", "0"))
    shard_count = int(get_env_var("SHARD_COUNT", "1"))
    ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    model_name = os.environ.get("TEACHER_MODEL", "phi3.5")
    s3_endpoint = os.environ.get("S3_ENDPOINT", "http://localhost:8333")
    s3_bucket = os.environ.get("S3_BUCKET", "datasets")
    prompt_file = os.environ.get("PROMPT_FILE", "prompts/teacher_prompt.txt")

    print(f"Starting Worker Shard {shard_index}/{shard_count}")
    print(f"Ollama URL: {ollama_url}, Model: {model_name}")

    teacher_prompt = load_prompt(prompt_file)

    # Resolve input dataset path
    local_pool = "data/commands_pool.jsonl"
    if not os.path.exists(local_pool):
        # Try downloading from S3
        print(f"Downloading {local_pool} from S3 bucket {s3_bucket}...")
        s3 = boto3.client(
            "s3",
            endpoint_url=s3_endpoint,
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "seaweedfs"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "seaweedfssecret")
        )
        os.makedirs("data", exist_ok=True)
        s3.download_file(s3_bucket, "commands_pool.jsonl", local_pool)

    out_dir = "datasets/teacher"
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"shard-{shard_index}.jsonl")

    processed = 0
    with open(local_pool, "r", encoding="utf-8") as f_in, open(out_file, "w", encoding="utf-8") as f_out:
        for idx, line in enumerate(f_in):
            if idx % shard_count != shard_index:
                continue
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            cmd_id = record["id"]
            cmd_text = record["text"]

            raw_reply = query_ollama(ollama_url, model_name, teacher_prompt, cmd_text)
            out_obj = {
                "id": cmd_id,
                "text": cmd_text,
                "teacher_raw": raw_reply
            }
            f_out.write(json.dumps(out_obj) + "\n")
            processed += 1
            if processed % 100 == 0:
                print(f"[Shard {shard_index}] Processed {processed} records...")

    print(f"[Shard {shard_index}] Completed. Wrote {processed} records to {out_file}")

    # Upload shard to SeaweedFS S3
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=s3_endpoint,
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "seaweedfs"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "seaweedfssecret")
        )
        s3_key = f"teacher/shard-{shard_index}.jsonl"
        s3.upload_file(out_file, s3_bucket, s3_key)
        print(f"[Shard {shard_index}] Successfully uploaded to s3://{s3_bucket}/{s3_key}")
    except Exception as e:
        print(f"[Shard {shard_index}] Note: S3 upload skipped or failed: {e}")

if __name__ == "__main__":
    main()
