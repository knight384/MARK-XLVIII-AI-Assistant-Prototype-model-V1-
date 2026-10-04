import { describe, expect, it } from 'bun:test';
import {
  NVIDIA_DEFAULT_MODEL,
  modelForOnboardingTest,
  onboardingDefaultModelRef,
  selectLiveNvidiaModel,
} from './llm-setup.ts';

describe('Anthropic onboarding model selection', () => {
  it('omits the curated model when testing a custom endpoint', () => {
    expect(modelForOnboardingTest('anthropic', true, 'claude-fable-5')).toBeUndefined();
  });

  it('keeps the selected model for official Anthropic and other providers', () => {
    expect(modelForOnboardingTest('anthropic', false, 'claude-fable-5')).toBe('claude-fable-5');
    expect(modelForOnboardingTest('openai', true, 'gpt-5-mini')).toBe('gpt-5-mini');
  });

  it('keeps a model picked from the discovered gateway catalog', () => {
    expect(modelForOnboardingTest('anthropic', true, 'gateway-large', ['gateway-fast', 'gateway-large']))
      .toBe('gateway-large');
  });

  it('re-discovers when the selection is not in the known catalog', () => {
    expect(modelForOnboardingTest('anthropic', true, 'claude-fable-5', ['gateway-fast']))
      .toBeUndefined();
  });

  it('saves the validated gateway model ahead of the curated selection', () => {
    expect(onboardingDefaultModelRef('anthropic', 'claude-fable-5', 'gateway-fast'))
      .toBe('anthropic:gateway-fast');
  });
});

describe('NVIDIA live catalog selection', () => {
  it('keeps a selection that remains in the live catalog', () => {
    expect(selectLiveNvidiaModel('publisher/current', ['publisher/current', NVIDIA_DEFAULT_MODEL]))
      .toBe('publisher/current');
  });

  it('replaces a retired selection with the preferred live model', () => {
    expect(selectLiveNvidiaModel('meta/llama-3.3-70b-instruct', ['other/chat', NVIDIA_DEFAULT_MODEL]))
      .toBe(NVIDIA_DEFAULT_MODEL);
  });

  it('tries the next preferred chat model before the alphabetical first', () => {
    expect(selectLiveNvidiaModel('retired', ['01-ai/yi-large', 'adept/fuyu-8b', 'openai/gpt-oss-20b']))
      .toBe('openai/gpt-oss-20b');
  });

  it('falls back predictably when no preferred model is available', () => {
    expect(selectLiveNvidiaModel('retired', ['first/live', 'second/live'])).toBe('first/live');
    expect(selectLiveNvidiaModel('retired', [])).toBe('retired');
  });
});
