/**
 * Unified Provider - Works with any OpenAI-compatible API
 *
 * Supports: OpenAI, Mistral, Qwen, Ollama, OpenRouter, HuggingFace, and any custom endpoint
 */

import { BaseProvider } from './base-provider';
import {
  Message,
  CompletionOptions,
  StreamChunk,
  TokenCost,
  ConfidenceTier,
  ProviderConfig,
  ModelInfo
} from './types';
import {
  ProviderId,
  PROVIDER_REGISTRY,
  ModelDefinition,
  getModelForTier
} from './provider-registry';

export class UnifiedProvider extends BaseProvider {
  private providerId: ProviderId;
  private models: ModelDefinition[];
  private authHeader: string;
  private authPrefix: string;

  constructor(config: ProviderConfig, providerId: ProviderId = 'custom') {
    super(config, config.name || providerId);

    this.providerId = providerId;
    const definition = PROVIDER_REGISTRY[providerId];

    this.authHeader = config.authHeader || definition?.authHeader || 'Authorization';
    this.authPrefix = config.authPrefix ?? definition?.authPrefix ?? 'Bearer';
    this.models = definition?.models || [];

    // Use custom base URL if provided, otherwise use registry default
    if (!this.baseUrl) {
      this.baseUrl = definition?.baseUrl;
    }
  }

  /**
   * Build authorization header value
   */
  private getAuthValue(): string {
    if (this.authPrefix) {
      return `${this.authPrefix} ${this.apiKey}`;
    }
    return this.apiKey;
  }

  /**
   * Complete a conversation with streaming response
   */
  async *complete(
    messages: Message[],
    options: CompletionOptions = {}
  ): AsyncGenerator<StreamChunk> {
    const model = options.model ||
      (options.confidenceTier
        ? this.getModelForTier(options.confidenceTier)
        : this.getDefaultModel());

    const maxTokens = options.maxTokens ?? 4096;
    const temperature = options.temperature ?? 0.7;
    const stream = options.stream !== false;

    // Convert messages to OpenAI format
    const openaiMessages = messages.map((msg) => ({
      role: msg.role,
      content: msg.content
    }));

    // Build headers
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      [this.authHeader]: this.getAuthValue()
    };

    // Add OpenRouter-specific headers if needed
    if (this.providerId === 'openrouter') {
      headers['HTTP-Referer'] = 'https://autonomi.dev';
      headers['X-Title'] = 'Autonomi Extension';
    }

    // Acquire rate limit token
    await this.rateLimiter.acquire();

    try {
      if (stream) {
        yield* this.streamCompletion(openaiMessages, model, maxTokens, temperature, headers, options.stopSequences);
      } else {
        yield* this.nonStreamCompletion(openaiMessages, model, maxTokens, temperature, headers, options.stopSequences);
      }
    } finally {
      this.rateLimiter.release();
    }
  }

  /**
   * Streaming completion
   */
  private async *streamCompletion(
    messages: Array<{ role: string; content: string }>,
    model: string,
    maxTokens: number,
    temperature: number,
    headers: Record<string, string>,
    stopSequences?: string[]
  ): AsyncGenerator<StreamChunk> {
    const response = await this.circuitBreaker.execute(async () => {
      const res = await fetch(`${this.baseUrl}/chat/completions`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          model,
          messages,
          max_tokens: maxTokens,
          temperature,
          stream: true,
          stop: stopSequences
        })
      });

      if (!res.ok) {
        const error = await res.text();
        throw new Error(`API error ${res.status}: ${error}`);
      }

      return res;
    });

    yield { type: 'message_start' };

    const reader = (response as Response).body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let totalInputTokens = 0;
    let totalOutputTokens = 0;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || trimmed === 'data: [DONE]') continue;

          if (trimmed.startsWith('data: ')) {
            try {
              const data = JSON.parse(trimmed.slice(6));

              // Handle content delta
              const content = data.choices?.[0]?.delta?.content;
              if (content) {
                yield {
                  type: 'content_block_delta',
                  content
                };
              }

              // Capture usage if provided
              if (data.usage) {
                totalInputTokens = data.usage.prompt_tokens || 0;
                totalOutputTokens = data.usage.completion_tokens || 0;
              }

              // Handle finish reason
              if (data.choices?.[0]?.finish_reason) {
                break;
              }
            } catch {
              // Skip malformed JSON
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    yield { type: 'content_block_stop' };
    yield {
      type: 'message_stop',
      usage: {
        inputTokens: totalInputTokens,
        outputTokens: totalOutputTokens,
        totalTokens: totalInputTokens + totalOutputTokens
      }
    };
  }

  /**
   * Non-streaming completion
   */
  private async *nonStreamCompletion(
    messages: Array<{ role: string; content: string }>,
    model: string,
    maxTokens: number,
    temperature: number,
    headers: Record<string, string>,
    stopSequences?: string[]
  ): AsyncGenerator<StreamChunk> {
    interface OpenAIResponse {
      choices?: Array<{ message?: { content?: string } }>;
      usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
    }

    const response = await this.circuitBreaker.execute(async () => {
      const res = await fetch(`${this.baseUrl}/chat/completions`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          model,
          messages,
          max_tokens: maxTokens,
          temperature,
          stream: false,
          stop: stopSequences
        })
      });

      if (!res.ok) {
        const error = await res.text();
        throw new Error(`API error ${res.status}: ${error}`);
      }

      return res.json();
    }) as OpenAIResponse;

    yield { type: 'message_start' };
    yield { type: 'content_block_start' };

    const content = response.choices?.[0]?.message?.content ?? '';
    yield {
      type: 'content_block_delta',
      content
    };

    yield { type: 'content_block_stop' };
    yield {
      type: 'message_stop',
      usage: {
        inputTokens: response.usage?.prompt_tokens ?? 0,
        outputTokens: response.usage?.completion_tokens ?? 0,
        totalTokens: response.usage?.total_tokens ?? 0
      }
    };
  }

  /**
   * Get default model for this provider
   */
  private getDefaultModel(): string {
    if (this.models.length > 0) {
      // Return a tier 2 model if available, otherwise first model
      const tier2 = this.models.find(m => m.tier === ConfidenceTier.TIER_2);
      return tier2?.id || this.models[0].id;
    }
    // Fallback defaults by provider
    switch (this.providerId) {
      case 'openai': return 'gpt-4o';
      case 'mistral': return 'mistral-large-latest';
      case 'qwen': return 'qwen-plus';
      case 'ollama': return 'llama3.2:latest';
      case 'openrouter': return 'anthropic/claude-3.5-sonnet';
      default: return 'gpt-4o';
    }
  }

  /**
   * Count tokens in text (estimation)
   */
  countTokens(text: string): number {
    // Use a simple approximation: ~4 characters per token for English
    // This is a rough estimate; actual tokenization varies by model
    return Math.ceil(text.length / 4);
  }

  /**
   * Get appropriate model for confidence tier
   */
  getModelForTier(tier: ConfidenceTier): string {
    const model = getModelForTier(this.providerId, tier);
    return model?.id || this.getDefaultModel();
  }

  /**
   * Get cost per token for a model
   */
  getCostPerToken(modelId: string): TokenCost {
    const model = this.models.find(m => m.id === modelId);
    if (model) {
      return {
        input: model.costPer1kInput / 1000,
        output: model.costPer1kOutput / 1000
      };
    }
    // Default costs (rough estimate)
    return { input: 0.001, output: 0.002 };
  }

  /**
   * Get available models
   */
  getAvailableModels(): ModelInfo[] {
    return this.models.map(m => ({
      id: m.id,
      name: m.name,
      contextWindow: m.contextWindow,
      maxOutputTokens: m.maxOutputTokens,
      cost: {
        input: m.costPer1kInput / 1000,
        output: m.costPer1kOutput / 1000
      },
      tier: m.tier
    }));
  }

  /**
   * Set custom models (for custom provider)
   */
  setModels(models: ModelDefinition[]): void {
    this.models = models;
  }

  /**
   * Validate API key by making a test request
   */
  async validateApiKey(): Promise<boolean> {
    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        [this.authHeader]: this.getAuthValue()
      };

      // Try to list models or make a minimal completion
      const res = await fetch(`${this.baseUrl}/models`, {
        method: 'GET',
        headers
      });

      return res.ok;
    } catch {
      return false;
    }
  }
}

/**
 * Create a provider for a specific provider ID
 */
export function createProvider(
  providerId: ProviderId,
  apiKey: string,
  customBaseUrl?: string
): UnifiedProvider {
  const definition = PROVIDER_REGISTRY[providerId];

  const config: ProviderConfig = {
    id: providerId,
    name: definition?.name || providerId,
    apiKey,
    baseUrl: customBaseUrl || definition?.baseUrl,
    authHeader: definition?.authHeader,
    authPrefix: definition?.authPrefix,
    isOpenAICompatible: definition?.isOpenAICompatible ?? true,
    supportsStreaming: definition?.supportsStreaming ?? true,
    timeout: 60000,
    maxRetries: 3,
    rateLimitRpm: 60
  };

  return new UnifiedProvider(config, providerId);
}

/**
 * Create a custom provider with any base URL
 */
export function createCustomProvider(
  name: string,
  baseUrl: string,
  apiKey: string,
  options: {
    authHeader?: 'Authorization' | 'X-API-Key' | 'Api-Key';
    authPrefix?: 'Bearer' | 'Api-Key' | '';
    models?: ModelDefinition[];
  } = {}
): UnifiedProvider {
  const config: ProviderConfig = {
    id: 'custom',
    name,
    apiKey,
    baseUrl,
    authHeader: options.authHeader || 'Authorization',
    authPrefix: options.authPrefix ?? 'Bearer',
    isOpenAICompatible: true,
    supportsStreaming: true,
    timeout: 60000,
    maxRetries: 3,
    rateLimitRpm: 60
  };

  const provider = new UnifiedProvider(config, 'custom');

  if (options.models) {
    provider.setModels(options.models);
  }

  return provider;
}
