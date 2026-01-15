/**
 * Provider types for Autonomi VSCode Extension
 */

// Confidence tiers for model routing
export enum ConfidenceTier {
  TIER_1 = 1, // Fast, cheap - simple tasks
  TIER_2 = 2, // Standard tasks
  TIER_3 = 3, // Complex tasks
  TIER_4 = 4  // High complexity, low confidence - needs powerful model
}

// Message role types
export type MessageRole = 'user' | 'assistant' | 'system';

// Message interface for conversation
export interface Message {
  role: MessageRole;
  content: string;
}

// Completion request options
export interface CompletionOptions {
  model?: string;
  maxTokens?: number;
  temperature?: number;
  stream?: boolean;
  topP?: number;
  stopSequences?: string[];
  confidenceTier?: ConfidenceTier;
}

// Stream chunk types
export type StreamChunkType =
  | 'content_block_start'
  | 'content_block_delta'
  | 'content_block_stop'
  | 'message_start'
  | 'message_delta'
  | 'message_stop'
  | 'error';

// Stream chunk interface
export interface StreamChunk {
  type: StreamChunkType;
  content?: string;
  usage?: TokenUsage;
  error?: ProviderError;
}

// Token usage tracking
export interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
}

// Cost per token for a model
export interface TokenCost {
  input: number;  // Cost per input token in USD
  output: number; // Cost per output token in USD
}

// Provider error interface
export interface ProviderError {
  code: string;
  message: string;
  retryable: boolean;
  statusCode?: number;
}

// Provider status
export interface ProviderStatus {
  name: string;
  available: boolean;
  circuitState: 'CLOSED' | 'OPEN' | 'HALF_OPEN';
  lastError?: ProviderError;
  lastSuccessTime?: number;
}

// Provider configuration
export interface ProviderConfig {
  id: string;
  name: string;
  apiKey: string;
  baseUrl?: string;
  authHeader?: 'Authorization' | 'X-API-Key' | 'Api-Key';
  authPrefix?: 'Bearer' | 'Api-Key' | '';
  isOpenAICompatible?: boolean;
  supportsStreaming?: boolean;
  timeout?: number;
  maxRetries?: number;
  rateLimitRpm?: number;
  rateLimitTpm?: number;
}

// Model information
export interface ModelInfo {
  id: string;
  name: string;
  contextWindow: number;
  maxOutputTokens: number;
  cost: TokenCost;
  tier: ConfidenceTier;
}
