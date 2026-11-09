#!/usr/bin/env python3
"""
Command Parsing Inference Microservice.
Provides /parse, /healthz, and /readyz endpoints.
Downloads student model from S3-compatible object storage at startup.
"""

import os
import sys
import json
import socket
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import boto3
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("inference_service")

# Required Environment Variables
MODEL_URI = os.environ.get("MODEL_URI", "models/v1")
MODEL_VERSION = os.environ.get("MODEL_VERSION", "v1")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://seaweedfs-s3.data.svc.cluster.local:8333")
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "64"))
FAULT_INJECT = os.environ.get("FAULT_INJECT", "0")
POD_NAME = os.environ.get("HOSTNAME", socket.gethostname())

# AWS / S3 Credentials from Secret
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "seaweedfs")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "seaweedfssecret")
S3_BUCKET = os.environ.get("S3_BUCKET", "models")

VALID_INTENTS = {
    "alarm_set", "alarm_query", "calendar_set", "calendar_query",
    "calendar_remove", "weather_query", "datetime_query", "recommendation_events"
}
REQUIRED_KEYS = {"intent", "date", "time", "place"}

# Global model state
state = {
    "model": None,
    "tokenizer": None,
    "ready": False
}

def download_model_from_s3(dest_dir="/app/model"):
    os.makedirs(dest_dir, exist_ok=True)
    logger.info(f"Connecting to S3 at {S3_ENDPOINT} (Bucket: {S3_BUCKET}, Prefix: {MODEL_URI})...")
    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY
    )
    try:
        paginator = s3.get_paginator("list_objects_v2")
        prefix = MODEL_URI.strip("/") + "/"
        downloaded = 0
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                rel_path = os.path.relpath(key, prefix)
                local_file = os.path.join(dest_dir, rel_path)
                os.makedirs(os.path.dirname(local_file), exist_ok=True)
                logger.info(f"Downloading s3://{S3_BUCKET}/{key} -> {local_file}")
                s3.download_file(S3_BUCKET, key, local_file)
                downloaded += 1
        logger.info(f"Downloaded {downloaded} files from S3.")
        return dest_dir
    except Exception as e:
        logger.warning(f"S3 download encountered issue: {e}. Checking local cache...")
        if os.path.exists(MODEL_URI):
            return MODEL_URI
        if os.path.exists("models/v1"):
            return "models/v1"
        return "EleutherAI/pythia-70m"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load model
    logger.info("Initializing inference service startup...")
    model_dir = download_model_from_s3()
    logger.info(f"Loading tokenizer and model from {model_dir}...")
    try:
        state["tokenizer"] = AutoTokenizer.from_pretrained(model_dir)
        if state["tokenizer"].pad_token is None:
            state["tokenizer"].pad_token = state["tokenizer"].eos_token
        state["model"] = AutoModelForCausalLM.from_pretrained(model_dir)
        state["model"].eval()
        state["ready"] = True
        logger.info("Model loaded successfully. Service is READY.")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        state["ready"] = False
    yield
    logger.info("Service shutting down.")

app = FastAPI(title="Command Parser Service", lifespan=lifespan)

class ParseRequest(BaseModel):
    text: str

def validate_schema(raw_text: str):
    """
    Validates the raw output string against schema.json.
    Returns parsed dict if valid, else None.
    """
    try:
        obj = json.loads(raw_text.strip())
    except Exception:
        return None

    if not isinstance(obj, dict):
        return None

    if set(obj.keys()) != REQUIRED_KEYS:
        return None

    if obj.get("intent") not in VALID_INTENTS:
        return None

    for slot in ["date", "time", "place"]:
        val = obj.get(slot)
        if val is not None and not isinstance(val, str):
            return None

    return obj

@app.get("/healthz")
def healthz():
    """Liveness probe: returns 200 as long as the process is alive."""
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "alive"})

@app.get("/readyz")
def readyz():
    """Readiness probe: returns 503 until model is loaded, 200 after."""
    if not state["ready"] or state["model"] is None:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"status": "loading"})
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ready"})

@app.post("/parse")
async def parse(req: ParseRequest, response: Response):
    # Set required tracking headers
    response.headers["X-Model-Version"] = MODEL_VERSION
    response.headers["X-Served-By"] = POD_NAME

    if not state["ready"] or state["model"] is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "service_not_ready"},
            headers=dict(response.headers)
        )

    # Generate inference prompt
    input_text = f"Command: {req.text}\nJSON:"
    inputs = state["tokenizer"](input_text, return_tensors="pt")

    with torch.no_grad():
        outputs = state["model"].generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            pad_token_id=state["tokenizer"].pad_token_id,
            do_sample=False
        )

    generated_text = state["tokenizer"].decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    
    # Fault Injection Hook
    current_fault_inject = os.environ.get("FAULT_INJECT", FAULT_INJECT)
    if str(current_fault_inject).strip() == "1":
        logger.warning("FAULT_INJECT=1 active: replacing model output with 'not json'")
        generated_text = "not json"

    # Validate output against schema.json
    parsed_json = validate_schema(generated_text)
    if parsed_json is None:
        logger.error(f"Schema validation failed for model output: {generated_text!r}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "invalid_model_output"},
            headers=dict(response.headers)
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=parsed_json,
        headers=dict(response.headers)
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
