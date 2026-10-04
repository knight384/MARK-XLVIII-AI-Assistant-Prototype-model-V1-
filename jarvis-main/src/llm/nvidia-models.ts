/**
 * NVIDIA's hosted chat default and the retired IDs that map onto supported
 * replacements. NVIDIA retires hosted endpoints on its own schedule (Llama 3.3
 * 70B went on 2026-08-26 and now answers HTTP 410), so saved "provider:model"
 * references are repaired the same way retired Groq IDs are (groq-models.ts).
 *
 * Only list IDs that are gone from NVIDIA's public /v1/models. A self-hosted
 * NIM is configured as openai_compatible, so this map never touches it.
 *
 * The dashboard mirrors NVIDIA_DEFAULT_MODEL in ui/src/v2/onboarding/llm-setup.ts.
 */
export const NVIDIA_DEFAULT_MODEL = 'nvidia/nemotron-3-super-120b-a12b';

export const NVIDIA_RETIRED_MODEL_REPLACEMENTS: Readonly<Record<string, string>> = {
  'meta/llama-3.3-70b-instruct': NVIDIA_DEFAULT_MODEL,
  'meta/llama-3.1-8b-instruct': 'openai/gpt-oss-20b',
  'google/gemma-2-2b-it': 'openai/gpt-oss-20b',
};
