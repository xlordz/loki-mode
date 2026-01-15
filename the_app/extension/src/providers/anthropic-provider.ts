/**
 * Anthropic Claude provider implementation
 */

import Anthropic from '@anthropic-ai/sdk';
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

// Anthropic model identifiers
export const ANTHROPIC_MODELS = {
  OPUS: 'claude-opus-4-5-20250514',
  SONNET: 'claude-sonnet-4-5-20250514',
  HAIKU: 'claude-haiku-3-5-20241022'
} as const;

// Model information with costs (as of 2025)
const MODEL_INFO: Record<string, ModelInfo> = {
  [ANTHROPIC_MODELS.OPUS]: {
    id: ANTHROPIC_MODELS.OPUS,
    name: 'Claude Opus 4.5',
    contextWindow: 200000,
    maxOutputTokens: 32000,
    cost: { input: 0.015, output: 0.075 }, // per 1K tokens
    tier: ConfidenceTier.TIER_4
  },
  [ANTHROPIC_MODELS.SONNET]: {
    id: ANTHROPIC_MODELS.SONNET,
    name: 'Claude Sonnet 4.5',
    contextWindow: 200000,
    maxOutputTokens: 16000,
    cost: { input: 0.003, output: 0.015 }, // per 1K tokens
    tier: ConfidenceTier.TIER_2
  },
  [ANTHROPIC_MODELS.HAIKU]: {
    id: ANTHROPIC_MODELS.HAIKU,
    name: 'Claude Haiku 3.5',
    contextWindow: 200000,
    maxOutputTokens: 8192,
    cost: { input: 0.0008, output: 0.004 }, // per 1K tokens
    tier: ConfidenceTier.TIER_1
  }
};

export class AnthropicProvider extends BaseProvider {
  private client: Anthropic;

  constructor(config: ProviderConfig) {
    super(config, 'anthropic');

    this.client = new Anthropic({
      apiKey: config.apiKey,
      baseURL: config.baseUrl,
      timeout: config.timeout ?? 60000,
      maxRetries: 0 // We handle retries ourselves
    });
  }

  /**
   * Complete a conversation with streaming response
   */
  async *complete(
    messages: Message[],
    options: CompletionOptions = {}
  ): AsyncGenerator<StreamChunk> {
    const model =
      options.model ??
      (options.confidenceTier
        ? this.getModelForTier(options.confidenceTier)
        : ANTHROPIC_MODELS.SONNET);

    const maxTokens = options.maxTokens ?? 4096;
    const temperature = options.temperature ?? 1.0;

    // Extract system message if present
    let systemMessage: string | undefined;
    const conversationMessages: Anthropic.MessageParam[] = [];

    for (const msg of messages) {
      if (msg.role === 'system') {
        systemMessage = msg.content;
      } else {
        conversationMessages.push({
          role: msg.role as 'user' | 'assistant',
          content: msg.content
        });
      }
    }

    // Acquire rate limit token before request
    await this.rateLimiter.acquire();

    try {
      if (options.stream !== false) {
        // Streaming mode
        yield* this.streamCompletion(
          conversationMessages,
          model,
          maxTokens,
          temperature,
          systemMessage,
          options.stopSequences
        );
      } else {
        // Non-streaming mode
        yield* this.nonStreamCompletion(
          conversationMessages,
          model,
          maxTokens,
          temperature,
          systemMessage,
          options.stopSequences
        );
      }
    } catch (error) {
      this.circuitBreaker.recordFailure();
      yield {
        type: 'error',
        error: this.toProviderError(error)
      };
    }
  }

  /**
   * Stream completion response
   */
  private async *streamCompletion(
    messages: Anthropic.MessageParam[],
    model: string,
    maxTokens: number,
    temperature: number,
    system?: string,
    stopSequences?: string[]
  ): AsyncGenerator<StreamChunk> {
    const stream = this.client.messages.stream({
      model,
      max_tokens: maxTokens,
      temperature,
      messages,
      system,
      stop_sequences: stopSequences
    });

    let inputTokens = 0;
    let outputTokens = 0;

    try {
      // Yield message start
      yield { type: 'message_start' };

      for await (const event of stream) {
        switch (event.type) {
          case 'message_start':
            if (event.message.usage) {
              inputTokens = event.message.usage.input_tokens;
            }
            break;

          case 'content_block_start':
            yield { type: 'content_block_start' };
            break;

          case 'content_block_delta':
            if (event.delta.type === 'text_delta') {
              yield {
                type: 'content_block_delta',
                content: event.delta.text
              };
            }
            break;

          case 'content_block_stop':
            yield { type: 'content_block_stop' };
            break;

          case 'message_delta':
            if (event.usage) {
              outputTokens = event.usage.output_tokens;
            }
            break;

          case 'message_stop':
            yield {
              type: 'message_stop',
              usage: {
                inputTokens,
                outputTokens,
                totalTokens: inputTokens + outputTokens
              }
            };
            break;
        }
      }

      this.circuitBreaker.recordSuccess();
    } catch (error) {
      this.circuitBreaker.recordFailure();
      throw error;
    }
  }

  /**
   * Non-streaming completion
   */
  private async *nonStreamCompletion(
    messages: Anthropic.MessageParam[],
    model: string,
    maxTokens: number,
    temperature: number,
    system?: string,
    stopSequences?: string[]
  ): AsyncGenerator<StreamChunk> {
    try {
      const response = await this.circuitBreaker.execute(async () => {
        return await this.client.messages.create({
          model,
          max_tokens: maxTokens,
          temperature,
          messages,
          system,
          stop_sequences: stopSequences
        });
      });

      yield { type: 'message_start' };
      yield { type: 'content_block_start' };

      // Extract text content
      for (const block of response.content) {
        if (block.type === 'text') {
          yield {
            type: 'content_block_delta',
            content: block.text
          };
        }
      }

      yield { type: 'content_block_stop' };
      yield {
        type: 'message_stop',
        usage: {
          inputTokens: response.usage.input_tokens,
          outputTokens: response.usage.output_tokens,
          totalTokens:
            response.usage.input_tokens + response.usage.output_tokens
        }
      };
    } catch (error) {
      throw error;
    }
  }

  /**
   * Count tokens in text
   * Uses a simple approximation since exact counting requires API call
   */
  countTokens(text: string): number {
    // Claude uses roughly 4 characters per token on average
    // This is an approximation - for exact counts, use the API
    return Math.ceil(text.length / 4);
  }

  /**
   * Get the appropriate model for a confidence tier
   * TIER_1: haiku (fast, cheap) - simple tasks
   * TIER_2: sonnet - standard tasks
   * TIER_3: sonnet - complex tasks
   * TIER_4: opus - low confidence, needs analysis
   */
  getModelForTier(tier: ConfidenceTier): string {
    switch (tier) {
      case ConfidenceTier.TIER_1:
        return ANTHROPIC_MODELS.HAIKU;
      case ConfidenceTier.TIER_2:
      case ConfidenceTier.TIER_3:
        return ANTHROPIC_MODELS.SONNET;
      case ConfidenceTier.TIER_4:
        return ANTHROPIC_MODELS.OPUS;
      default:
        return ANTHROPIC_MODELS.SONNET;
    }
  }

  /**
   * Get cost per token for a model
   * Returns cost per token (not per 1K tokens)
   */
  getCostPerToken(model: string): TokenCost {
    const info = MODEL_INFO[model];
    if (!info) {
      // Default to Sonnet pricing if unknown model
      return {
        input: 0.003 / 1000,
        output: 0.015 / 1000
      };
    }
    return {
      input: info.cost.input / 1000,
      output: info.cost.output / 1000
    };
  }

  /**
   * Get available models
   */
  getAvailableModels(): ModelInfo[] {
    return Object.values(MODEL_INFO);
  }

  /**
   * Validate API key by making a small request
   */
  async validateApiKey(): Promise<boolean> {
    try {
      // Make a minimal API call to validate the key
      await this.client.messages.create({
        model: ANTHROPIC_MODELS.HAIKU,
        max_tokens: 1,
        messages: [{ role: 'user', content: 'test' }]
      });
      return true;
    } catch (error) {
      if (
        error instanceof Error &&
        (error.message.includes('401') ||
          error.message.includes('unauthorized') ||
          error.message.includes('invalid_api_key'))
      ) {
        return false;
      }
      // Other errors might be rate limits etc, assume key is valid
      return true;
    }
  }

  /**
   * Count tokens using estimation (more accurate API method not available)
   */
  async countTokensAccurate(messages: Message[]): Promise<number> {
    // Use estimation since count_tokens API is not available in current SDK
    return messages.reduce((acc, m) => acc + this.countTokens(m.content), 0);
  }
}
