/** A custom Anthropic gateway chooses from its own catalog, not our curated IDs. */
export function modelForOnboardingTest(
  provider: string,
  customEndpoint: boolean,
  selectedModel: string,
  discoveredModels?: string[] | null,
): string | undefined {
  if (provider !== 'anthropic' || !customEndpoint) return selectedModel;
  // Until the gateway catalog is known, omit the model so the daemon
  // discovers and validates one. Once known, the user's pick from that
  // catalog is authoritative and gets validated as-is.
  return discoveredModels?.includes(selectedModel) ? selectedModel : undefined;
}

/** Persist the exact model that passed the connection test when available. */
export function onboardingDefaultModelRef(
  provider: string,
  selectedModel: string,
  validatedModel?: string,
): string {
  return `${provider}:${validatedModel || selectedModel || 'default'}`;
}

/** NVIDIA's hosted chat default. Mirrors src/llm/nvidia-models.ts. */
export const NVIDIA_DEFAULT_MODEL = 'nvidia/nemotron-3-super-120b-a12b';

/**
 * Offline fallback list and seed preference, best first. NVIDIA's live
 * catalog mixes chat, embedding and vision models in alphabetical order, so
 * its first entry is not a safe model to seed.
 */
export const NVIDIA_FALLBACK_MODELS: readonly string[] = [NVIDIA_DEFAULT_MODEL, 'openai/gpt-oss-20b'];

/** The best preferred NVIDIA chat model the catalog still serves, if any. */
export function preferredNvidiaModel(models: readonly string[]): string | undefined {
  return NVIDIA_FALLBACK_MODELS.find((model) => models.includes(model));
}

/** Keep a valid selection when NVIDIA refreshes its rotating catalog. */
export function selectLiveNvidiaModel(current: string, models: readonly string[]): string {
  if (models.includes(current)) return current;
  return preferredNvidiaModel(models) ?? models[0] ?? current;
}
