# API Keys Guide

## Autonomous Research Scientist Agent — Multi-Agent AI Lab

---

## Overview

The AI Research Agent needs **one API key** to function: an **LLM (Large Language Model) API key**. The system uses the LLM for paper summarization, gap analysis, hypothesis generation, experiment code generation, evaluation, and report writing.

The arXiv paper retrieval uses a **free public API** and requires no key.

---

## Supported LLM Providers

You can use any of the following providers. The system uses the **OpenAI-compatible API format**, so any provider that implements this standard will work.

---

### 1. OpenAI (Recommended for best quality)

**Models:** `gpt-4o-mini` (fast, cheap), `gpt-4o` (highest quality), `gpt-4-turbo`

#### How to Get Your API Key

1. Go to [https://platform.openai.com/signup](https://platform.openai.com/signup)
2. Create an account or sign in
3. Navigate to [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)
4. Click **"Create new secret key"**
5. Give it a name (e.g., "AI Research Agent")
6. Copy the key — it starts with `sk-`

#### Configuration in the App

| Setting | Value |
|---------|-------|
| **API Key** | `sk-your-key-here` |
| **Base URL** | `https://api.openai.com/v1` |
| **Model** | `gpt-4o-mini` or `gpt-4o` |

#### Pricing

- **gpt-4o-mini**: ~$0.15 / 1M input tokens, ~$0.60 / 1M output tokens (very affordable)
- **gpt-4o**: ~$2.50 / 1M input tokens, ~$10 / 1M output tokens
- A typical research session costs approximately **$0.05–$0.50** depending on the model

#### Documentation

- [OpenAI API Documentation](https://platform.openai.com/docs/api-reference)
- [OpenAI Pricing](https://openai.com/api/pricing/)
- [API Key Best Practices](https://platform.openai.com/docs/guides/safety-best-practices)

---

### 2. Groq (Recommended for speed — Free Tier Available!)

**Models:** `llama-3.3-70b-versatile`, `deepseek-r1-distill-llama-70b`, `mixtral-8x7b-32768`

#### How to Get Your API Key

1. Go to [https://console.groq.com/](https://console.groq.com/)
2. Sign up with Google or email
3. Navigate to [https://console.groq.com/keys](https://console.groq.com/keys)
4. Click **"Create API Key"**
5. Copy the key — it starts with `gsk_`

#### Configuration in the App

| Setting | Value |
|---------|-------|
| **API Key** | `gsk_your-key-here` |
| **Base URL** | `https://api.groq.com/openai/v1` |
| **Model** | `llama-3.3-70b-versatile` |

#### Pricing

- **Free tier**: 14,400 requests/day for most models
- No credit card required
- Extremely fast inference (fastest available)

#### Documentation

- [Groq Console](https://console.groq.com/)
- [Groq API Documentation](https://console.groq.com/docs/quickstart)
- [Supported Models](https://console.groq.com/docs/models)

---

### 3. OpenRouter (Access to 100+ models)

**Models:** `google/gemini-2.0-flash-001`, `anthropic/claude-3.5-sonnet`, `meta-llama/llama-3.3-70b-instruct`, and many more

#### How to Get Your API Key

1. Go to [https://openrouter.ai/](https://openrouter.ai/)
2. Sign up and log in
3. Navigate to [https://openrouter.ai/keys](https://openrouter.ai/keys)
4. Click **"Create Key"**
5. Copy the key — it starts with `sk-or-`

#### Configuration in the App

| Setting | Value |
|---------|-------|
| **API Key** | `sk-or-your-key-here` |
| **Base URL** | `https://openrouter.ai/api/v1` |
| **Model** | `google/gemini-2.0-flash-001` |

#### Pricing

- Some models have **free tiers**
- Pay-per-use for premium models
- Credits start from $5

#### Documentation

- [OpenRouter Documentation](https://openrouter.ai/docs)
- [Model List & Pricing](https://openrouter.ai/models)

---

### 4. Local LLMs (via Ollama or LM Studio)

You can also run models locally for **completely free** usage (no API key needed, but you need sufficient hardware).

#### Using Ollama

1. Install Ollama: [https://ollama.ai/](https://ollama.ai/)
2. Pull a model: `ollama pull llama3.1`
3. Ollama automatically starts a local API server

#### Configuration in the App

| Setting | Value |
|---------|-------|
| **API Key** | `ollama` (any non-empty string) |
| **Base URL** | `http://localhost:11434/v1` |
| **Model** | `llama3.1` |

#### Using LM Studio

1. Download LM Studio: [https://lmstudio.ai/](https://lmstudio.ai/)
2. Download a model (e.g., Llama 3.1, Mistral)
3. Start the local server in LM Studio

#### Configuration in the App

| Setting | Value |
|---------|-------|
| **API Key** | `lm-studio` (any non-empty string) |
| **Base URL** | `http://localhost:1234/v1` |
| **Model** | Name of your loaded model |

---

## How to Configure in the App

1. Open the app at `http://localhost:8000`
2. Click the **⚙️ Settings** button in the top-right corner
3. Enter your **API Key**
4. Set the **Base URL** (or use a quick preset button)
5. Choose your **Model**
6. Click **Save Configuration**

The green "Configured" badge will appear in the header when your settings are saved.

---

## Security Notes

- API keys are stored **in memory only** — they are never saved to disk
- Keys are transmitted to the server over localhost and used only for LLM API calls
- When the server restarts, you need to re-enter your key
- **Never commit API keys to Git** — use the settings UI instead

---

## Troubleshooting

| Issue | Solution |
|-------|---------|
| "API key not configured" error | Open Settings and enter your API key |
| "401 Unauthorized" from LLM | Your API key is invalid or expired — generate a new one |
| "429 Rate Limit" | You've hit the provider's rate limit — wait or upgrade your plan |
| "Connection refused" (local LLM) | Make sure Ollama/LM Studio server is running |
| Slow responses | Try Groq (fastest) or a smaller model like `gpt-4o-mini` |
| Poor quality outputs | Try a larger model like `gpt-4o` or `llama-3.3-70b` |

---

## Quick Comparison

| Provider | Speed | Quality | Cost | Ease of Setup |
|----------|-------|---------|------|---------------|
| **Groq** | ⚡ Fastest | ★★★★ | Free tier available | ★★★★★ |
| **OpenAI** | ★★★ | ★★★★★ | $0.05–$0.50/session | ★★★★ |
| **OpenRouter** | ★★★ | ★★★★ | Varies by model | ★★★★ |
| **Ollama (local)** | ★★ | ★★★ | Free (needs GPU) | ★★★ |

---
