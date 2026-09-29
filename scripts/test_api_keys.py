#!/usr/bin/env python3
"""Diagnostic script to test and verify all API keys in .env file."""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

UA = "SignalpostKeyVerifier/1.0"


def test_gemini(key: str) -> tuple[bool, str]:
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
        payload = json.dumps({"contents": [{"parts": [{"text": "Reply with 'OK'"}]}]}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            data = json.loads(resp.read().decode())
            txt = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return True, f"Connected (response: {txt[:20]})"
    except Exception as e:
        return False, str(e)


def test_groq(key: str) -> tuple[bool, str]:
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = json.dumps({"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            return True, "Connected (Llama 3.3 70B responding)"
    except Exception as e:
        return False, str(e)


def test_mistral(key: str) -> tuple[bool, str]:
    try:
        url = "https://api.mistral.ai/v1/chat/completions"
        payload = json.dumps({"model": "mistral-small-latest", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            return True, "Connected (Mistral Small responding)"
    except Exception as e:
        return False, str(e)


def test_huggingface(key: str) -> tuple[bool, str]:
    try:
        url = "https://api-inference.huggingface.co/models/Qwen/Qwen2.5-72B-Instruct"
        payload = json.dumps({"inputs": "Hello", "parameters": {"max_new_tokens": 5}}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            return True, "Connected (Qwen 2.5 72B responding)"
    except Exception as e:
        return False, str(e)


def test_brave(key: str) -> tuple[bool, str]:
    try:
        url = "https://api.search.brave.com/res/v1/web/search?q=Equinor&count=1"
        req = urllib.request.Request(url, headers={"X-Subscription-Token": key, "Accept": "application/json", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            return True, "Connected (Brave Web Search responding)"
    except Exception as e:
        return False, str(e)


def test_tavily(key: str) -> tuple[bool, str]:
    try:
        url = "https://api.tavily.com/search"
        payload = json.dumps({"api_key": key, "query": "Equinor ASA Norway", "max_results": 1}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            return True, "Connected (Tavily AI Search responding)"
    except Exception as e:
        return False, str(e)


def main() -> None:
    print("=" * 65)
    print("SIGNALPOST API KEYS VERIFICATION DIAGNOSTIC")
    print("=" * 65)

    keys = {
        "GEMINI_API_KEY": ("Google Gemini 1.5 Flash (Free)", test_gemini),
        "GROQ_API_KEY": ("Groq Llama 3.3 70B (Free)", test_groq),
        "MISTRAL_API_KEY": ("Mistral AI (Free tier)", test_mistral),
        "HUGGINGFACE_API_KEY": ("Hugging Face Qwen (Free)", test_huggingface),
        "BRAVE_API_KEY": ("Brave Search API (Free tier)", test_brave),
        "TAVILY_API_KEY": ("Tavily AI Search (Free tier)", test_tavily),
    }

    active_count = 0
    for env_var, (name, test_func) in keys.items():
        val = os.getenv(env_var, "").strip()
        if not val:
            print(f"[-] {name:38} : NOT SET in .env (Autonomous Free Mode)")
        else:
            masked = val[:4] + "..." + val[-4:] if len(val) > 8 else "***"
            ok, msg = test_func(val)
            if ok:
                active_count += 1
                print(f"[+] {name:38} : VALID & LIVE ({masked}) - {msg}")
            else:
                print(f"[!] {name:38} : ERROR ({masked}) - {msg}")

    print("=" * 65)
    print(f"Summary: {active_count}/{len(keys)} free external APIs verified and connected.")
    print("Note: Brønnøysund, NAV Arbeidsplassen, Google News RSS, and NorBERT")
    print("are 100% open public government engines that require NO keys.")
    print("=" * 65)


if __name__ == "__main__":
    main()
