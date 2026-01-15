/**
 * Multi-Provider Manager - Manages multiple LLM providers with fallback
 *
 * Supports: Anthropic, OpenAI, Google, Mistral, Qwen, Ollama, HuggingFace, OpenRouter, Custom
 */

import * as vscode from 'vscode';
import { BaseProvider } from './base-provider';
import { AnthropicProvider } from './anthropic-provider';
import { UnifiedProvider, createProvider, createCustomProvider } from './unified-provider';
import {
  Message,
  CompletionOptions,
  StreamChunk,
  ProviderConfig,
  ProviderStatus,
  ConfidenceTier
} from './types';
import {
  ProviderId,
  PROVIDER_REGISTRY,
  getAllProviders,
  getProvider
} from './provider-registry';

export interface ProviderCredentials {
  providerId: ProviderId;
  apiKey: string;
  baseUrl?: string;  // Optional custom URL (for Ollama, custom endpoints)
  enabled: boolean;
}

export class MultiProviderManager {
  private providers: Map<ProviderId, BaseProvider> = new Map();
  private credentials: Map<ProviderId, ProviderCredentials> = new Map();
  private fallbackOrder: ProviderId[] = [];
  private preferredProvider: ProviderId = 'anthropic';
  private context: vscode.ExtensionContext;

  constructor(context: vscode.ExtensionContext) {
    this.context = context;
  }

  /**
   * Initialize providers from stored credentials
   */
  async initialize(): Promise<void> {
    // Load credentials from secret storage
    const providers = getAllProviders();

    for (const def of providers) {
      if (def.id === 'custom') continue;

      const apiKey = await this.context.secrets.get(`autonomi.apiKey.${def.id}`);
      const baseUrl = await this.context.secrets.get(`autonomi.baseUrl.${def.id}`);

      if (apiKey || !def.requiresApiKey) {
        this.credentials.set(def.id, {
          providerId: def.id,
          apiKey: apiKey || '',
          baseUrl: baseUrl || def.baseUrl,
          enabled: true
        });
      }
    }

    // Load custom providers
    const customProviders = await this.loadCustomProviders();
    for (const custom of customProviders) {
      this.credentials.set('custom', custom);
    }

    // Initialize active providers
    await this.initializeProviders();

    // Set fallback order from config
    const config = vscode.workspace.getConfiguration('autonomi');
    this.preferredProvider = config.get('provider.preferred', 'anthropic') as ProviderId;
    this.fallbackOrder = config.get('provider.fallbacks', ['openai', 'openrouter', 'ollama']) as ProviderId[];
  }

  /**
   * Load custom provider configurations
   */
  private async loadCustomProviders(): Promise<ProviderCredentials[]> {
    const customJson = await this.context.secrets.get('autonomi.customProviders');
    if (customJson) {
      try {
        return JSON.parse(customJson);
      } catch {
        return [];
      }
    }
    return [];
  }

  /**
   * Initialize provider instances from credentials
   */
  private async initializeProviders(): Promise<void> {
    this.providers.clear();

    for (const [id, creds] of this.credentials) {
      if (!creds.enabled) continue;

      try {
        const provider = this.createProviderInstance(creds);
        if (provider) {
          this.providers.set(id, provider);
        }
      } catch (error) {
        console.error(`Failed to initialize provider ${id}:`, error);
      }
    }
  }

  /**
   * Create a provider instance from credentials
   */
  private createProviderInstance(creds: ProviderCredentials): BaseProvider | undefined {
    const def = getProvider(creds.providerId);
    if (!def) return undefined;

    // Use native Anthropic provider for better API support
    if (creds.providerId === 'anthropic') {
      return new AnthropicProvider({
        id: 'anthropic',
        name: 'Anthropic',
        apiKey: creds.apiKey,
        baseUrl: creds.baseUrl
      });
    }

    // Use unified provider for all OpenAI-compatible APIs
    if (def.isOpenAICompatible) {
      return createProvider(creds.providerId, creds.apiKey, creds.baseUrl);
    }

    // For non-OpenAI-compatible APIs, use unified provider with appropriate settings
    return createProvider(creds.providerId, creds.apiKey, creds.baseUrl);
  }

  /**
   * Add or update provider credentials
   */
  async setProviderCredentials(
    providerId: ProviderId,
    apiKey: string,
    baseUrl?: string
  ): Promise<void> {
    // Store in secret storage
    await this.context.secrets.store(`autonomi.apiKey.${providerId}`, apiKey);
    if (baseUrl) {
      await this.context.secrets.store(`autonomi.baseUrl.${providerId}`, baseUrl);
    }

    // Update local credentials
    this.credentials.set(providerId, {
      providerId,
      apiKey,
      baseUrl,
      enabled: true
    });

    // Re-initialize provider
    const creds = this.credentials.get(providerId);
    if (creds) {
      const provider = this.createProviderInstance(creds);
      if (provider) {
        this.providers.set(providerId, provider);
      }
    }
  }

  /**
   * Add a custom provider
   */
  async addCustomProvider(
    name: string,
    baseUrl: string,
    apiKey: string
  ): Promise<void> {
    const provider = createCustomProvider(name, baseUrl, apiKey);
    this.providers.set('custom', provider);

    // Store credentials
    await this.context.secrets.store('autonomi.apiKey.custom', apiKey);
    await this.context.secrets.store('autonomi.baseUrl.custom', baseUrl);
    await this.context.secrets.store('autonomi.name.custom', name);

    this.credentials.set('custom', {
      providerId: 'custom',
      apiKey,
      baseUrl,
      enabled: true
    });
  }

  /**
   * Remove provider credentials
   */
  async removeProvider(providerId: ProviderId): Promise<void> {
    await this.context.secrets.delete(`autonomi.apiKey.${providerId}`);
    await this.context.secrets.delete(`autonomi.baseUrl.${providerId}`);

    this.credentials.delete(providerId);
    this.providers.delete(providerId);
  }

  /**
   * Get available providers (configured and ready)
   */
  getAvailableProviders(): ProviderId[] {
    return Array.from(this.providers.keys());
  }

  /**
   * Get provider status
   */
  getProviderStatus(providerId: ProviderId): ProviderStatus | undefined {
    const provider = this.providers.get(providerId);
    if (!provider) return undefined;

    return {
      name: provider.getName(),
      available: provider.isAvailable(),
      circuitState: provider.getCircuitState()
    };
  }

  /**
   * Get all provider statuses
   */
  getAllProviderStatuses(): Map<ProviderId, ProviderStatus> {
    const statuses = new Map<ProviderId, ProviderStatus>();

    for (const [id, provider] of this.providers) {
      statuses.set(id, {
        name: provider.getName(),
        available: provider.isAvailable(),
        circuitState: provider.getCircuitState()
      });
    }

    return statuses;
  }

  /**
   * Complete with automatic fallback
   */
  async *complete(
    messages: Message[],
    options: CompletionOptions = {}
  ): AsyncGenerator<StreamChunk> {
    const providersToTry = [
      this.preferredProvider,
      ...this.fallbackOrder.filter(p => p !== this.preferredProvider)
    ];

    let lastError: Error | undefined;

    for (const providerId of providersToTry) {
      const provider = this.providers.get(providerId);
      if (!provider || !provider.isAvailable()) {
        continue;
      }

      try {
        yield* provider.complete(messages, options);
        return; // Success - exit
      } catch (error) {
        lastError = error as Error;
        console.warn(`Provider ${providerId} failed, trying fallback:`, error);
        continue;
      }
    }

    // All providers failed
    yield {
      type: 'error',
      error: {
        code: 'ALL_PROVIDERS_FAILED',
        message: lastError?.message || 'All providers failed',
        retryable: false
      }
    };
  }

  /**
   * Complete with a specific provider
   */
  async *completeWith(
    providerId: ProviderId,
    messages: Message[],
    options: CompletionOptions = {}
  ): AsyncGenerator<StreamChunk> {
    const provider = this.providers.get(providerId);
    if (!provider) {
      yield {
        type: 'error',
        error: {
          code: 'PROVIDER_NOT_FOUND',
          message: `Provider ${providerId} not configured`,
          retryable: false
        }
      };
      return;
    }

    yield* provider.complete(messages, options);
  }

  /**
   * Get recommended model for confidence tier
   */
  getModelForTier(tier: ConfidenceTier): { providerId: ProviderId; model: string } | undefined {
    // Try preferred provider first
    const preferredProvider = this.providers.get(this.preferredProvider);
    if (preferredProvider) {
      return {
        providerId: this.preferredProvider,
        model: preferredProvider.getModelForTier(tier)
      };
    }

    // Try fallbacks
    for (const providerId of this.fallbackOrder) {
      const provider = this.providers.get(providerId);
      if (provider && provider.isAvailable()) {
        return {
          providerId,
          model: provider.getModelForTier(tier)
        };
      }
    }

    return undefined;
  }

  /**
   * Count tokens using the preferred provider
   */
  countTokens(text: string): number {
    const provider = this.providers.get(this.preferredProvider) ||
      this.providers.values().next().value;

    if (provider) {
      return provider.countTokens(text);
    }

    // Fallback estimation
    return Math.ceil(text.length / 4);
  }

  /**
   * Set preferred provider
   */
  setPreferredProvider(providerId: ProviderId): void {
    if (this.providers.has(providerId)) {
      this.preferredProvider = providerId;
    }
  }

  /**
   * Set fallback order
   */
  setFallbackOrder(order: ProviderId[]): void {
    this.fallbackOrder = order;
  }

  /**
   * Check if any provider is available
   */
  hasAvailableProvider(): boolean {
    for (const provider of this.providers.values()) {
      if (provider.isAvailable()) {
        return true;
      }
    }
    return false;
  }

  /**
   * Validate provider API key
   */
  async validateProviderKey(providerId: ProviderId): Promise<boolean> {
    const provider = this.providers.get(providerId);
    if (!provider) return false;

    if ('validateApiKey' in provider && typeof provider.validateApiKey === 'function') {
      return (provider as AnthropicProvider | UnifiedProvider).validateApiKey();
    }

    // Try a simple completion
    try {
      const gen = provider.complete(
        [{ role: 'user', content: 'test' }],
        { maxTokens: 1 }
      );

      for await (const chunk of gen) {
        if (chunk.type === 'error') {
          return false;
        }
      }
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Dispose of all providers
   */
  dispose(): void {
    this.providers.clear();
    this.credentials.clear();
  }
}
