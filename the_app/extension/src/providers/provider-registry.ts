/**
 * Provider Registry - Supports multiple LLM providers
 *
 * Supported providers:
 * - Anthropic (Claude)
 * - OpenAI (GPT-4, o1)
 * - Mistral
 * - Qwen (Alibaba)
 * - Ollama (local)
 * - HuggingFace
 * - OpenRouter (multi-provider gateway)
 * - Any OpenAI-compatible API
 */

import { ConfidenceTier, ProviderConfig, ModelInfo } from './types';

// Provider identifiers
export type ProviderId =
  | 'anthropic'
  | 'openai'
  | 'google'
  | 'mistral'
  | 'qwen'
  | 'ollama'
  | 'huggingface'
  | 'openrouter'
  | 'custom';

// Provider metadata
export interface ProviderDefinition {
  id: ProviderId;
  name: string;
  description: string;
  baseUrl: string;
  authHeader: 'Authorization' | 'X-API-Key' | 'Api-Key';
  authPrefix: 'Bearer' | 'Api-Key' | '';
  models: ModelDefinition[];
  isOpenAICompatible: boolean;
  requiresApiKey: boolean;
  supportsStreaming: boolean;
}

export interface ModelDefinition {
  id: string;
  name: string;
  contextWindow: number;
  maxOutputTokens: number;
  costPer1kInput: number;  // USD per 1k tokens
  costPer1kOutput: number; // USD per 1k tokens
  tier: ConfidenceTier;    // Recommended confidence tier
  capabilities: string[];
}

// Provider definitions with default configurations
export const PROVIDER_REGISTRY: Record<ProviderId, ProviderDefinition> = {
  anthropic: {
    id: 'anthropic',
    name: 'Anthropic',
    description: 'Claude models from Anthropic',
    baseUrl: 'https://api.anthropic.com',
    authHeader: 'X-API-Key',
    authPrefix: '',
    isOpenAICompatible: false,
    requiresApiKey: true,
    supportsStreaming: true,
    models: [
      {
        id: 'claude-opus-4-5-20251101',
        name: 'Claude Opus 4.5',
        contextWindow: 200000,
        maxOutputTokens: 32000,
        costPer1kInput: 0.015,
        costPer1kOutput: 0.075,
        tier: ConfidenceTier.TIER_4,
        capabilities: ['reasoning', 'coding', 'analysis', 'planning']
      },
      {
        id: 'claude-sonnet-4-20250514',
        name: 'Claude Sonnet 4',
        contextWindow: 200000,
        maxOutputTokens: 64000,
        costPer1kInput: 0.003,
        costPer1kOutput: 0.015,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'analysis', 'general']
      },
      {
        id: 'claude-haiku-3-5-20241022',
        name: 'Claude Haiku 3.5',
        contextWindow: 200000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.0008,
        costPer1kOutput: 0.004,
        tier: ConfidenceTier.TIER_1,
        capabilities: ['fast', 'simple-tasks']
      }
    ]
  },

  openai: {
    id: 'openai',
    name: 'OpenAI',
    description: 'GPT and o1 models from OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    authHeader: 'Authorization',
    authPrefix: 'Bearer',
    isOpenAICompatible: true,
    requiresApiKey: true,
    supportsStreaming: true,
    models: [
      {
        id: 'gpt-4o',
        name: 'GPT-4o',
        contextWindow: 128000,
        maxOutputTokens: 16384,
        costPer1kInput: 0.0025,
        costPer1kOutput: 0.01,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'analysis', 'multimodal']
      },
      {
        id: 'gpt-4o-mini',
        name: 'GPT-4o Mini',
        contextWindow: 128000,
        maxOutputTokens: 16384,
        costPer1kInput: 0.00015,
        costPer1kOutput: 0.0006,
        tier: ConfidenceTier.TIER_1,
        capabilities: ['fast', 'coding', 'general']
      },
      {
        id: 'o1',
        name: 'o1',
        contextWindow: 200000,
        maxOutputTokens: 100000,
        costPer1kInput: 0.015,
        costPer1kOutput: 0.06,
        tier: ConfidenceTier.TIER_4,
        capabilities: ['reasoning', 'complex-problems']
      },
      {
        id: 'o1-mini',
        name: 'o1 Mini',
        contextWindow: 128000,
        maxOutputTokens: 65536,
        costPer1kInput: 0.003,
        costPer1kOutput: 0.012,
        tier: ConfidenceTier.TIER_3,
        capabilities: ['reasoning', 'coding']
      }
    ]
  },

  google: {
    id: 'google',
    name: 'Google AI',
    description: 'Gemini models from Google',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta',
    authHeader: 'X-API-Key',
    authPrefix: '',
    isOpenAICompatible: false, // Uses different API format
    requiresApiKey: true,
    supportsStreaming: true,
    models: [
      {
        id: 'gemini-2.0-flash-exp',
        name: 'Gemini 2.0 Flash',
        contextWindow: 1000000,
        maxOutputTokens: 8192,
        costPer1kInput: 0,  // Currently free in experimental
        costPer1kOutput: 0,
        tier: ConfidenceTier.TIER_1,
        capabilities: ['fast', 'coding', 'multimodal', 'long-context']
      },
      {
        id: 'gemini-1.5-pro',
        name: 'Gemini 1.5 Pro',
        contextWindow: 2000000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.00125,
        costPer1kOutput: 0.005,
        tier: ConfidenceTier.TIER_3,
        capabilities: ['coding', 'analysis', 'multimodal', 'long-context']
      },
      {
        id: 'gemini-1.5-flash',
        name: 'Gemini 1.5 Flash',
        contextWindow: 1000000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.000075,
        costPer1kOutput: 0.0003,
        tier: ConfidenceTier.TIER_1,
        capabilities: ['fast', 'coding', 'general']
      },
      {
        id: 'gemini-1.5-flash-8b',
        name: 'Gemini 1.5 Flash 8B',
        contextWindow: 1000000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.0000375,
        costPer1kOutput: 0.00015,
        tier: ConfidenceTier.TIER_1,
        capabilities: ['fast', 'simple-tasks']
      }
    ]
  },

  mistral: {
    id: 'mistral',
    name: 'Mistral AI',
    description: 'Mistral and Codestral models',
    baseUrl: 'https://api.mistral.ai/v1',
    authHeader: 'Authorization',
    authPrefix: 'Bearer',
    isOpenAICompatible: true,
    requiresApiKey: true,
    supportsStreaming: true,
    models: [
      {
        id: 'mistral-large-latest',
        name: 'Mistral Large',
        contextWindow: 128000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.002,
        costPer1kOutput: 0.006,
        tier: ConfidenceTier.TIER_3,
        capabilities: ['coding', 'analysis', 'multilingual']
      },
      {
        id: 'mistral-medium-latest',
        name: 'Mistral Medium',
        contextWindow: 32000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.0027,
        costPer1kOutput: 0.0081,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'general']
      },
      {
        id: 'mistral-small-latest',
        name: 'Mistral Small',
        contextWindow: 32000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.0002,
        costPer1kOutput: 0.0006,
        tier: ConfidenceTier.TIER_1,
        capabilities: ['fast', 'simple-tasks']
      },
      {
        id: 'codestral-latest',
        name: 'Codestral',
        contextWindow: 32000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.0003,
        costPer1kOutput: 0.0009,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'code-completion']
      }
    ]
  },

  qwen: {
    id: 'qwen',
    name: 'Qwen (Alibaba)',
    description: 'Qwen models via DashScope API',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    authHeader: 'Authorization',
    authPrefix: 'Bearer',
    isOpenAICompatible: true,
    requiresApiKey: true,
    supportsStreaming: true,
    models: [
      {
        id: 'qwen-max',
        name: 'Qwen Max',
        contextWindow: 32000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.004,
        costPer1kOutput: 0.012,
        tier: ConfidenceTier.TIER_3,
        capabilities: ['coding', 'analysis', 'multilingual']
      },
      {
        id: 'qwen-plus',
        name: 'Qwen Plus',
        contextWindow: 131072,
        maxOutputTokens: 8192,
        costPer1kInput: 0.0008,
        costPer1kOutput: 0.002,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'general', 'long-context']
      },
      {
        id: 'qwen-turbo',
        name: 'Qwen Turbo',
        contextWindow: 131072,
        maxOutputTokens: 8192,
        costPer1kInput: 0.0003,
        costPer1kOutput: 0.0006,
        tier: ConfidenceTier.TIER_1,
        capabilities: ['fast', 'simple-tasks']
      },
      {
        id: 'qwen-coder-plus',
        name: 'Qwen Coder Plus',
        contextWindow: 131072,
        maxOutputTokens: 8192,
        costPer1kInput: 0.0014,
        costPer1kOutput: 0.0028,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'code-completion']
      }
    ]
  },

  ollama: {
    id: 'ollama',
    name: 'Ollama',
    description: 'Local models via Ollama',
    baseUrl: 'http://localhost:11434/v1',
    authHeader: 'Authorization',
    authPrefix: 'Bearer',
    isOpenAICompatible: true,
    requiresApiKey: false,
    supportsStreaming: true,
    models: [
      {
        id: 'llama3.3:70b',
        name: 'Llama 3.3 70B',
        contextWindow: 128000,
        maxOutputTokens: 8192,
        costPer1kInput: 0,  // Local - no cost
        costPer1kOutput: 0,
        tier: ConfidenceTier.TIER_3,
        capabilities: ['coding', 'analysis', 'general']
      },
      {
        id: 'llama3.2:latest',
        name: 'Llama 3.2',
        contextWindow: 128000,
        maxOutputTokens: 8192,
        costPer1kInput: 0,
        costPer1kOutput: 0,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'general']
      },
      {
        id: 'codellama:latest',
        name: 'Code Llama',
        contextWindow: 16384,
        maxOutputTokens: 4096,
        costPer1kInput: 0,
        costPer1kOutput: 0,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'code-completion']
      },
      {
        id: 'deepseek-coder-v2:latest',
        name: 'DeepSeek Coder V2',
        contextWindow: 128000,
        maxOutputTokens: 8192,
        costPer1kInput: 0,
        costPer1kOutput: 0,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'code-completion']
      },
      {
        id: 'qwen2.5-coder:latest',
        name: 'Qwen 2.5 Coder',
        contextWindow: 32768,
        maxOutputTokens: 8192,
        costPer1kInput: 0,
        costPer1kOutput: 0,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'code-completion']
      }
    ]
  },

  huggingface: {
    id: 'huggingface',
    name: 'HuggingFace',
    description: 'Models via HuggingFace Inference API',
    baseUrl: 'https://api-inference.huggingface.co/models',
    authHeader: 'Authorization',
    authPrefix: 'Bearer',
    isOpenAICompatible: false, // HF has its own format
    requiresApiKey: true,
    supportsStreaming: true,
    models: [
      {
        id: 'meta-llama/Llama-3.3-70B-Instruct',
        name: 'Llama 3.3 70B Instruct',
        contextWindow: 128000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.0009,
        costPer1kOutput: 0.0009,
        tier: ConfidenceTier.TIER_3,
        capabilities: ['coding', 'analysis', 'general']
      },
      {
        id: 'Qwen/Qwen2.5-Coder-32B-Instruct',
        name: 'Qwen 2.5 Coder 32B',
        contextWindow: 32768,
        maxOutputTokens: 8192,
        costPer1kInput: 0.0008,
        costPer1kOutput: 0.0008,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'code-completion']
      },
      {
        id: 'deepseek-ai/DeepSeek-Coder-V2-Instruct',
        name: 'DeepSeek Coder V2',
        contextWindow: 128000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.0014,
        costPer1kOutput: 0.0028,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'analysis']
      }
    ]
  },

  openrouter: {
    id: 'openrouter',
    name: 'OpenRouter',
    description: 'Multi-provider gateway with 200+ models',
    baseUrl: 'https://openrouter.ai/api/v1',
    authHeader: 'Authorization',
    authPrefix: 'Bearer',
    isOpenAICompatible: true,
    requiresApiKey: true,
    supportsStreaming: true,
    models: [
      // Anthropic via OpenRouter
      {
        id: 'anthropic/claude-3.5-sonnet',
        name: 'Claude 3.5 Sonnet (OR)',
        contextWindow: 200000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.003,
        costPer1kOutput: 0.015,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'analysis', 'general']
      },
      // OpenAI via OpenRouter
      {
        id: 'openai/gpt-4o',
        name: 'GPT-4o (OR)',
        contextWindow: 128000,
        maxOutputTokens: 16384,
        costPer1kInput: 0.0025,
        costPer1kOutput: 0.01,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'analysis', 'multimodal']
      },
      // DeepSeek
      {
        id: 'deepseek/deepseek-chat',
        name: 'DeepSeek Chat',
        contextWindow: 64000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.00014,
        costPer1kOutput: 0.00028,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'analysis']
      },
      {
        id: 'deepseek/deepseek-coder',
        name: 'DeepSeek Coder',
        contextWindow: 64000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.00014,
        costPer1kOutput: 0.00028,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'code-completion']
      },
      // Mistral via OpenRouter
      {
        id: 'mistralai/mistral-large',
        name: 'Mistral Large (OR)',
        contextWindow: 128000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.002,
        costPer1kOutput: 0.006,
        tier: ConfidenceTier.TIER_3,
        capabilities: ['coding', 'analysis']
      },
      // Meta Llama
      {
        id: 'meta-llama/llama-3.3-70b-instruct',
        name: 'Llama 3.3 70B (OR)',
        contextWindow: 128000,
        maxOutputTokens: 8192,
        costPer1kInput: 0.0004,
        costPer1kOutput: 0.0004,
        tier: ConfidenceTier.TIER_2,
        capabilities: ['coding', 'analysis', 'general']
      },
      // Google
      {
        id: 'google/gemini-2.0-flash-exp:free',
        name: 'Gemini 2.0 Flash (Free)',
        contextWindow: 1000000,
        maxOutputTokens: 8192,
        costPer1kInput: 0,
        costPer1kOutput: 0,
        tier: ConfidenceTier.TIER_1,
        capabilities: ['fast', 'general', 'long-context']
      }
    ]
  },

  custom: {
    id: 'custom',
    name: 'Custom Provider',
    description: 'Any OpenAI-compatible API endpoint',
    baseUrl: '',
    authHeader: 'Authorization',
    authPrefix: 'Bearer',
    isOpenAICompatible: true,
    requiresApiKey: true,
    supportsStreaming: true,
    models: []
  }
};

/**
 * Get provider definition by ID
 */
export function getProvider(id: ProviderId): ProviderDefinition {
  return PROVIDER_REGISTRY[id];
}

/**
 * Get all providers
 */
export function getAllProviders(): ProviderDefinition[] {
  return Object.values(PROVIDER_REGISTRY);
}

/**
 * Get models for a provider
 */
export function getModelsForProvider(providerId: ProviderId): ModelDefinition[] {
  return PROVIDER_REGISTRY[providerId]?.models ?? [];
}

/**
 * Get model by ID across all providers
 */
export function getModelById(modelId: string): { provider: ProviderDefinition; model: ModelDefinition } | undefined {
  for (const provider of Object.values(PROVIDER_REGISTRY)) {
    const model = provider.models.find(m => m.id === modelId);
    if (model) {
      return { provider, model };
    }
  }
  return undefined;
}

/**
 * Get recommended model for a confidence tier from a provider
 */
export function getModelForTier(providerId: ProviderId, tier: ConfidenceTier): ModelDefinition | undefined {
  const provider = PROVIDER_REGISTRY[providerId];
  if (!provider) return undefined;

  // Find exact match first
  let model = provider.models.find(m => m.tier === tier);
  if (model) return model;

  // Find closest tier (prefer lower tier = more capable)
  const tierOrder = [ConfidenceTier.TIER_4, ConfidenceTier.TIER_3, ConfidenceTier.TIER_2, ConfidenceTier.TIER_1];
  const targetIndex = tierOrder.indexOf(tier);

  for (let i = targetIndex; i < tierOrder.length; i++) {
    model = provider.models.find(m => m.tier === tierOrder[i]);
    if (model) return model;
  }

  // Fall back to first available model
  return provider.models[0];
}

/**
 * Calculate cost for a request
 */
export function calculateRequestCost(
  model: ModelDefinition,
  inputTokens: number,
  outputTokens: number
): number {
  const inputCost = (inputTokens / 1000) * model.costPer1kInput;
  const outputCost = (outputTokens / 1000) * model.costPer1kOutput;
  return inputCost + outputCost;
}

/**
 * Create provider config from definition and user settings
 */
export function createProviderConfig(
  definition: ProviderDefinition,
  apiKey: string,
  customBaseUrl?: string
): ProviderConfig {
  return {
    id: definition.id,
    name: definition.name,
    apiKey,
    baseUrl: customBaseUrl || definition.baseUrl,
    authHeader: definition.authHeader,
    authPrefix: definition.authPrefix,
    isOpenAICompatible: definition.isOpenAICompatible,
    supportsStreaming: definition.supportsStreaming,
    timeout: 60000,
    maxRetries: 3,
    rateLimitRpm: 60
  };
}
