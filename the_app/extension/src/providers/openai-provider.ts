/**
 * OpenAI provider implementation (stub)
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

// OpenAI model identifiers
export const OPENAI_MODELS = {
  GPT4O: 'gpt-4o',
  GPT4_TURBO: 'gpt-4-turbo',
  GPT4O_MINI: 'gpt-4o-mini'
} as const;

// Model information with costs (as of 2025)
const MODEL_INFO: Record<string, ModelInfo> = {
  [OPENAI_MODELS.GPT4O]: {
    id: OPENAI_MODELS.GPT4O,
    name: 'GPT-4o',
    contextWindow: 128000,
    maxOutputTokens: 16384,
    cost: { input: 0.0025, output: 0.01 }, // per 1K tokens
    tier: ConfidenceTier.TIER_3
  },
  [OPENAI_MODELS.GPT4_TURBO]: {
    id: OPENAI_MODELS.GPT4_TURBO,
    name: 'GPT-4 Turbo',
    contextWindow: 128000,
    maxOutputTokens: 4096,
    cost: { input: 0.01, output: 0.03 }, // per 1K tokens
    tier: ConfidenceTier.TIER_4
  },
  [OPENAI_MODELS.GPT4O_MINI]: {
    id: OPENAI_MODELS.GPT4O_MINI,
    name: 'GPT-4o Mini',
    contextWindow: 128000,
    maxOutputTokens: 16384,
    cost: { input: 0.00015, output: 0.0006 }, // per 1K tokens
    tier: ConfidenceTier.TIER_1
  }
};

export class OpenAIProvider extends BaseProvider {
  protected openaiBaseUrl: string;

  constructor(config: ProviderConfig) {
    super(config, 'openai');
    this.openaiBaseUrl = config.baseUrl ?? 'https://api.openai.com/v1';
  }

  /**
   * Complete a conversation with streaming response
   * TODO: Implement full OpenAI SDK integration
   */
  async *complete(
    messages: Message[],
    options: CompletionOptions = {}
  ): AsyncGenerator<StreamChunk> {
    const model =
      options.model ??
      (options.confidenceTier
        ? this.getModelForTier(options.confidenceTier)
        : OPENAI_MODELS.GPT4O);

    const maxTokens = options.maxTokens ?? 4096;
    const temperature = options.temperature ?? 1.0;

    // Convert messages to OpenAI format
    const openaiMessages = messages.map((msg) => ({
      role: msg.role,
      content: msg.content
    }));

    // Acquire rate limit token
    await this.rateLimiter.acquire();

    try {
      if (options.stream !== false) {
        yield* this.streamCompletion(
          openaiMessages,
          model,
          maxTokens,
          temperature,
          options.stopSequences
        );
      } else {
        yield* this.nonStreamCompletion(
          openaiMessages,
          model,
          maxTokens,
          temperature,
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
   * Stream completion response using fetch
   * TODO: Replace with official OpenAI SDK
   */
  private async *streamCompletion(
    messages: Array<{ role: string; content: string }>,
    model: string,
    maxTokens: number,
    temperature: number,
    stopSequences?: string[]
  ): AsyncGenerator<StreamChunk> {
    const response = await this.circuitBreaker.execute(async () => {
      return await fetch(`${this.openaiBaseUrl}/chat/completions`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model,
          messages,
          max_tokens: maxTokens,
          temperature,
          stream: true,
          stop: stopSequences
        })
      });
    });

    if (!response.ok) {
      throw new Error(`OpenAI API error: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    yield { type: 'message_start' };
    yield { type: 'content_block_start' };

    let totalOutputTokens = 0;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') {
              continue;
            }

            try {
              const parsed = JSON.parse(data);
              const delta = parsed.choices?.[0]?.delta;

              if (delta?.content) {
                yield {
                  type: 'content_block_delta',
                  content: delta.content
                };
                // Rough token estimation for output
                totalOutputTokens += Math.ceil(delta.content.length / 4);
              }
            } catch {
              // Skip malformed JSON
            }
          }
        }
      }

      yield { type: 'content_block_stop' };
      yield {
        type: 'message_stop',
        usage: {
          inputTokens: this.countTokensForMessages(messages),
          outputTokens: totalOutputTokens,
          totalTokens: this.countTokensForMessages(messages) + totalOutputTokens
        }
      };

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
    messages: Array<{ role: string; content: string }>,
    model: string,
    maxTokens: number,
    temperature: number,
    stopSequences?: string[]
  ): AsyncGenerator<StreamChunk> {
    interface OpenAIResponse {
      choices?: Array<{ message?: { content?: string } }>;
      usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
    }
    const response = await this.circuitBreaker.execute(async () => {
      const res = await fetch(`${this.openaiBaseUrl}/chat/completions`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json'
        },
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
        throw new Error(`OpenAI API error: ${res.status}`);
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
   * Count tokens in text
   * Uses a simple approximation
   */
  countTokens(text: string): number {
    // GPT models use roughly 4 characters per token
    return Math.ceil(text.length / 4);
  }

  /**
   * Count tokens for message array
   */
  private countTokensForMessages(
    messages: Array<{ role: string; content: string }>
  ): number {
    let tokens = 0;
    for (const msg of messages) {
      tokens += this.countTokens(msg.content);
      tokens += 4; // Overhead per message
    }
    return tokens;
  }

  /**
   * Get the appropriate model for a confidence tier
   * TIER_1: gpt-4o-mini (fast, cheap)
   * TIER_2: gpt-4o
   * TIER_3: gpt-4o
   * TIER_4: gpt-4-turbo (for complex analysis)
   */
  getModelForTier(tier: ConfidenceTier): string {
    switch (tier) {
      case ConfidenceTier.TIER_1:
        return OPENAI_MODELS.GPT4O_MINI;
      case ConfidenceTier.TIER_2:
      case ConfidenceTier.TIER_3:
        return OPENAI_MODELS.GPT4O;
      case ConfidenceTier.TIER_4:
        return OPENAI_MODELS.GPT4_TURBO;
      default:
        return OPENAI_MODELS.GPT4O;
    }
  }

  /**
   * Get cost per token for a model
   */
  getCostPerToken(model: string): TokenCost {
    const info = MODEL_INFO[model];
    if (!info) {
      // Default to GPT-4o pricing
      return {
        input: 0.0025 / 1000,
        output: 0.01 / 1000
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
   * Validate API key
   */
  async validateApiKey(): Promise<boolean> {
    try {
      const response = await fetch(`${this.openaiBaseUrl}/models`, {
        headers: {
          Authorization: `Bearer ${this.apiKey}`
        }
      });
      return response.ok;
    } catch {
      return false;
    }
  }
}
