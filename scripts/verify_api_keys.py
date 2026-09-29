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


def check_gemini(key: str) -> tuple[bool, str]:
    models = ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-3.8-flash"]
    for m in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
            payload = json.dumps({"contents": [{"parts": [{"text": "Reply with 'OK'"}]}]}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode())
                txt = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return True, f"Connected ({m}, response: {txt[:20]})"
        except urllib.error.HTTPError as e:
            if e.code in (404, 503):
                continue
            try:
                err = json.loads(e.read().decode())
                msg = err.get("error", {}).get("message") or str(e)
                return False, f"HTTP {e.code}: {msg}"
            except Exception:
                return False, f"HTTP {e.code}: {e.reason}"
        except Exception as e:
            return False, str(e)
    return False, "No active Gemini models found"


def check_groq(key: str) -> tuple[bool, str]:
    models = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    for m in models:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            payload = json.dumps({"model": m, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": UA})
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                return True, f"Connected (model: {m})"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            try:
                err = json.loads(e.read().decode())
                return False, f"HTTP {e.code}: {err.get('error', {}).get('message')}"
            except Exception:
                return False, f"HTTP {e.code}: {e.reason}"
        except Exception as e:
            return False, str(e)
    return False, "No active Groq models available"


def check_mistral(key: str) -> tuple[bool, str]:
    try:
        url = "https://api.mistral.ai/v1/chat/completions"
        payload = json.dumps({"model": "mistral-small-latest", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            return True, "Connected (Mistral Small responding)"
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode())
            msg = err.get("error", {}).get("message") or str(e)
            return False, f"HTTP {e.code}: {msg}"
        except Exception:
            return False, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return False, str(e)


def check_huggingface(key: str) -> tuple[bool, str]:
    try:
        url = "https://router.huggingface.co/v1/chat/completions"
        payload = json.dumps({
            "model": "meta-llama/Llama-3.1-8B-Instruct",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            return True, "Connected (Llama 3.1 8B via HF Router)"
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode())
            msg = err.get("error") or str(e)
            return False, f"HTTP {e.code}: {msg}"
        except Exception:
            return False, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return False, str(e)


def check_brave(key: str) -> tuple[bool, str]:
    try:
        url = "https://api.search.brave.com/res/v1/web/search?q=Equinor&count=1"
        req = urllib.request.Request(url, headers={"X-Subscription-Token": key, "Accept": "application/json", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            return True, "Connected (Brave Web Search responding)"
    except Exception as e:
        return False, str(e)


def check_tavily(key: str) -> tuple[bool, str]:
    try:
        url = "https://api.tavily.com/search"
        payload = json.dumps({"api_key": key, "query": "Equinor ASA Norway", "max_results": 1}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            return True, "Connected (Tavily AI Search responding)"
    except Exception as e:
        return False, str(e)


def check_google_places(key: str) -> tuple[bool, str]:
    try:
        url = "https://places.googleapis.com/v1/places:searchText"
        payload = json.dumps({"textQuery": "Equinor Stavanger Norway"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.id",
                "User-Agent": UA,
            },
        )
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            data = json.loads(resp.read().decode())
            count = len(data.get("places", []))
            return True, f"Connected (Places API New, found {count} results)"
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode())
            return False, f"HTTP {e.code}: {err.get('error', {}).get('message')}"
        except Exception:
            return False, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return False, str(e)


def main() -> None:
    print("=" * 70)
    print("SIGNALPOST API KEYS & TOKENS VERIFICATION DIAGNOSTIC")
    print("=" * 70)

    # 1. 100% Free Tools & Tokens (NO Credit Card Required)
    print("\n--- [1. 100% FREE TOOLS & TOKENS (No Credit Card Required)] ---")
    free_tools = {
        "GEMINI_API_KEY": ("Google Gemini 1.5 Flash", check_gemini),
        "GROQ_API_KEY": ("Groq Llama / Qwen", check_groq),
        "TAVILY_API_KEY": ("Tavily AI Search (1,000 queries/mo)", check_tavily),
        "HUGGINGFACE_TOKEN": ("Hugging Face User Access Token", check_huggingface),
    }

    free_active = 0
    for env_var, (name, test_func) in free_tools.items():
        val = os.getenv(env_var, "").strip()
        # Fallback check for huggingface alias
        if not val and env_var == "HUGGINGFACE_TOKEN":
            val = (os.getenv("HF_TOKEN", "") or os.getenv("HUGGINGFACE_API_KEY", "")).strip()

        if not val:
            print(f"[-] {name:40} : NOT SET in .env (Autonomous Free Mode)")
        else:
            masked = val[:4] + "..." + val[-4:] if len(val) > 8 else "***"
            ok, msg = test_func(val)
            if ok:
                free_active += 1
                print(f"[+] {name:40} : VALID & LIVE ({masked}) - {msg}")
            else:
                print(f"[!] {name:40} : ERROR ({masked}) - {msg}")

    # 2. Paid Commercial Services (Credit Card / Billing Setup Required)
    print("\n--- [2. PAID COMMERCIAL SERVICES (Credit Card / Billing Required)] ---")
    paid_tools = {
        "GOOGLE_PLACES_API_KEY": ("Google Places API", check_google_places),
        "BRAVE_API_KEY": ("Brave Search API", check_brave),
        "MISTRAL_API_KEY": ("Mistral AI API", check_mistral),
    }

    paid_active = 0
    for env_var, (name, test_func) in paid_tools.items():
        val = os.getenv(env_var, "").strip()
        if not val:
            print(f"[-] {name:40} : NOT SET in .env (Skipped)")
        else:
            masked = val[:4] + "..." + val[-4:] if len(val) > 8 else "***"
            ok, msg = test_func(val)
            if ok:
                paid_active += 1
                print(f"[+] {name:40} : VALID & LIVE ({masked}) - {msg}")
            else:
                print(f"[!] {name:40} : ERROR ({masked}) - {msg}")

    print("\n" + "=" * 70)
    print(f"Summary: {free_active}/{len(free_tools)} Free tools + {paid_active}/{len(paid_tools)} Paid tools active.")
    print("Zero-Key Built-ins (100% Free Always Active):")
    print("  * Brønnøysund Enhetsregisteret & Kunngjøringer APIs")
    print("  * NAV Arbeidsplassen Official Job Vacancies API")
    print("  * Gule Sider / Eniro Official Business Directory")
    print("  * Google News RSS Norwegian Sentiment Feed")
    print("  * NorBERT Local Neural Legal/Financial Arbiter")
    print("=" * 70)


if __name__ == "__main__":
    main()
