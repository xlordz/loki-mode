/**
 * Provider exports for Autonomi VSCode Extension
 *
 * Supported Providers:
 * - Anthropic (Claude)
 * - OpenAI (GPT-4, o1)
 * - Google (Gemini)
 * - Mistral
 * - Qwen (Alibaba)
 * - Ollama (local)
 * - HuggingFace
 * - OpenRouter (multi-provider gateway)
 * - Custom (any OpenAI-compatible API)
 */

// Types
export * from './types';

// Infrastructure
export { RateLimiter, createRpmLimiter, createTpmLimiter } from './rate-limiter';
export {
  CircuitBreaker,
  CircuitOpenError,
  type CircuitState,
  type CircuitBreakerConfig,
  type CircuitBreakerStats
} from './circuit-breaker';

// Base provider
export { BaseProvider } from './base-provider';

// Provider implementations
export { AnthropicProvider, ANTHROPIC_MODELS } from './anthropic-provider';
export { OpenAIProvider, OPENAI_MODELS } from './openai-provider';

// Unified provider (works with all OpenAI-compatible APIs)
export {
  UnifiedProvider,
  createProvider,
  createCustomProvider
} from './unified-provider';

// Provider registry (all supported providers and models)
export {
  type ProviderId,
  type ProviderDefinition,
  type ModelDefinition,
  PROVIDER_REGISTRY,
  getProvider,
  getAllProviders,
  getModelsForProvider,
  getModelById,
  getModelForTier,
  calculateRequestCost,
  createProviderConfig
} from './provider-registry';

// Multi-provider manager with fallback
export {
  MultiProviderManager,
  type ProviderCredentials
} from './multi-provider-manager';

// Legacy provider manager (for backward compatibility)
export { ProviderManager, type ProviderManagerConfig } from './provider-manager';
