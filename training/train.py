#!/usr/bin/env python3
"""
Sequence-Level Knowledge Distillation Training Script.
Fine-tunes EleutherAI/pythia-70m on CPU using Hugging Face Transformers.
"""

import os
import sys
import yaml
import json
import random
import hashlib
import argparse
import numpy as np
import torch
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    Trainer,
    TrainingArguments,
    DataCollatorForLanguageModeling
)
from datasets import Dataset

def compute_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def compute_dir_sha256(dir_path, output_sha_file):
    hashes = []
    for root, _, files in sorted(os.walk(dir_path)):
        for f in sorted(files):
            if f == os.path.basename(output_sha_file):
                continue
            fp = os.path.join(root, f)
            h = compute_sha256(fp)
            rel_path = os.path.relpath(fp, dir_path)
            hashes.append(f"{h}  {rel_path}")
    combined_content = "\n".join(hashes) + "\n"
    overall_sha = hashlib.sha256(combined_content.encode("utf-8")).hexdigest()
    with open(output_sha_file, "w", encoding="utf-8") as f:
        f.write(f"{overall_sha}\n")
        f.write(combined_content)
    return overall_sha

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

def load_config(config_path="training/config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def format_example(record):
    cmd_text = record["text"]
    # Build strict 4-key JSON string
    target_json = json.dumps({
        "intent": record["intent"],
        "date": record["date"],
        "time": record["time"],
        "place": record["place"]
    })
    return f"Command: {cmd_text}\nJSON: {target_json}"

def main():
    parser = argparse.ArgumentParser(description="Train Student Model")
    parser.add_argument("--config", default="training/config.yaml", help="Path to config file")
    parser.add_argument("--subset", type=int, default=None, help="Subset size for quick validation")
    parser.add_argument("--version", default="v1", choices=["v1", "v2"], help="Model version")
    args = parser.parse_args()

    cfg = load_config(args.config)
    seed = cfg.get("seed", 42)
    set_seed(seed)

    # Determine subset limit
    env_subset = os.environ.get("SUBSET")
    if args.subset is not None:
        max_samples = args.subset
    elif env_subset:
        max_samples = int(env_subset)
    else:
        max_samples = 1500  # Default per project requirement

    model_name = cfg.get("model", {}).get("name_or_path", "EleutherAI/pythia-70m")
    out_dir = f"models/{args.version}"
    os.makedirs(out_dir, exist_ok=True)
    loss_csv = cfg.get("model", {}).get("loss_log", "training/loss.csv")
    os.makedirs(os.path.dirname(loss_csv), exist_ok=True)

    print(f"=== Knowledge Distillation Training ({args.version}) ===")
    print(f"Base Model: {model_name}")
    print(f"Training on CPU | Max Samples: {max_samples} | Seed: {seed}")

    # Load dataset
    data_path = "datasets/v1/train.jsonl"
    if not os.path.exists(data_path):
        sys.exit(f"Error: {data_path} not found. Run worker/clean.py first.")

    raw_data = []
    with open(data_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx >= max_samples:
                break
            line = line.strip()
            if line:
                raw_data.append(json.loads(line))

    formatted_texts = [format_example(r) for r in raw_data]
    print(f"Loaded {len(formatted_texts)} training examples.")

    # Tokenizer & Model
    print(f"Loading tokenizer and model: {model_name}...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(model_name)

    # Tokenize
    max_seq_len = cfg.get("max_seq_length", 128)
    def tokenize_fn(examples):
        enc = tokenizer(examples["text"], truncation=True, max_length=max_seq_len, padding="max_length")
        enc["labels"] = enc["input_ids"].copy()
        return enc

    hf_dataset = Dataset.from_dict({"text": formatted_texts})
    tokenized_dataset = hf_dataset.map(tokenize_fn, batched=True, remove_columns=["text"])

    num_epochs = cfg.get("epochs", 3)
    if args.version == "v2":
        num_epochs += 1  # Version 2 has an additional epoch

    lr = float(cfg.get("learning_rate", 5e-5))
    batch_size = cfg.get("batch_size", 8)

    training_args = TrainingArguments(
        output_dir=f"training/checkpoints_{args.version}",
        overwrite_output_dir=True,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        learning_rate=lr,
        weight_decay=0.01,
        logging_steps=10,
        save_strategy="epoch",
        use_cpu=True,
        seed=seed,
        report_to="none"
    )

    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=data_collator,
    )

    print("Beginning training...")
    train_result = trainer.train()

    # Save epoch losses
    loss_history = []
    for log in trainer.state.log_history:
        if "loss" in log and "epoch" in log:
            loss_history.append((round(log["epoch"]), log["loss"]))

    # Deduplicate and group by epoch
    epoch_losses = {}
    for ep, l in loss_history:
        epoch_losses[ep] = l

    with open(loss_csv, "w", encoding="utf-8") as f_loss:
        f_loss.write("epoch,loss\n")
        for ep in sorted(epoch_losses.keys()):
            f_loss.write(f"{ep},{epoch_losses[ep]:.4f}\n")

    print(f"Training completed. Final loss recorded in {loss_csv}.")

    # Save model and tokenizer
    print(f"Saving model and tokenizer to {out_dir}...")
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)

    # Compute checksum
    sha_file = os.path.join(out_dir, "model.sha256")
    overall_sha = compute_dir_sha256(out_dir, sha_file)
    print(f"Model Checksum ({args.version}): {overall_sha}")
    print(f"Checksum file saved to {sha_file}")

if __name__ == "__main__":
    main()
