/**
 * Onboarding / Quick Start flow for Autonomi Extension
 * Shows on first install or when no provider is configured
 */

import * as vscode from 'vscode';
import {
  ProviderId,
  PROVIDER_REGISTRY,
  getAllProviders,
  ModelDefinition
} from '../providers/provider-registry';

// Provider display info with icons
const PROVIDER_DISPLAY: Record<ProviderId, { label: string; description: string; icon: string }> = {
  anthropic: {
    label: 'Anthropic',
    description: 'Claude Opus, Sonnet, Haiku',
    icon: '$(hubot)'
  },
  openai: {
    label: 'OpenAI',
    description: 'GPT-4o, o1, GPT-4 Turbo',
    icon: '$(sparkle)'
  },
  google: {
    label: 'Google',
    description: 'Gemini 2.0, 1.5 Pro/Flash',
    icon: '$(globe)'
  },
  mistral: {
    label: 'Mistral AI',
    description: 'Mistral Large, Codestral',
    icon: '$(zap)'
  },
  qwen: {
    label: 'Qwen (Alibaba)',
    description: 'Qwen Max, Plus, Coder',
    icon: '$(ruby)'
  },
  ollama: {
    label: 'Ollama (Local)',
    description: 'Free - Run models locally',
    icon: '$(server)'
  },
  huggingface: {
    label: 'HuggingFace',
    description: 'Inference API models',
    icon: '$(smiley)'
  },
  openrouter: {
    label: 'OpenRouter',
    description: '200+ models, free tier available',
    icon: '$(radio-tower)'
  },
  custom: {
    label: 'Custom / Other',
    description: 'Any OpenAI-compatible API',
    icon: '$(settings-gear)'
  }
};

interface OnboardingState {
  providerId?: ProviderId;
  apiKey?: string;
  baseUrl?: string;
  modelId?: string;
}

/**
 * Show the quick start onboarding flow
 */
export async function showOnboarding(context: vscode.ExtensionContext): Promise<OnboardingState | undefined> {
  const state: OnboardingState = {};

  // Step 1: Select Provider
  const provider = await showProviderSelection();
  if (!provider) return undefined;
  state.providerId = provider;

  // Step 2: Configure based on provider type
  if (provider === 'custom') {
    // Custom provider flow
    const customConfig = await showCustomProviderSetup();
    if (!customConfig) return undefined;
    state.baseUrl = customConfig.baseUrl;
    state.apiKey = customConfig.apiKey;
    state.modelId = customConfig.modelId;
  } else if (provider === 'ollama') {
    // Ollama flow - no API key needed
    const ollamaConfig = await showOllamaSetup();
    if (!ollamaConfig) return undefined;
    state.baseUrl = ollamaConfig.baseUrl;
    state.modelId = ollamaConfig.modelId;
  } else {
    // Standard provider flow
    const apiKey = await showApiKeyInput(provider);
    if (!apiKey) return undefined;
    state.apiKey = apiKey;

    // Select model
    const model = await showModelSelection(provider);
    if (!model) return undefined;
    state.modelId = model;
  }

  // Save configuration
  await saveOnboardingConfig(context, state);

  // Show success message
  vscode.window.showInformationMessage(
    `Autonomi configured with ${PROVIDER_DISPLAY[state.providerId].label}. Run "Autonomi: Start Task" to begin.`,
    'Start Task'
  ).then(action => {
    if (action === 'Start Task') {
      vscode.commands.executeCommand('autonomi.startTask');
    }
  });

  return state;
}

/**
 * Step 1: Provider Selection
 */
async function showProviderSelection(): Promise<ProviderId | undefined> {
  const providers = getAllProviders().filter(p => p.id !== 'custom');

  const items: vscode.QuickPickItem[] = [
    // Featured providers first
    {
      label: `${PROVIDER_DISPLAY.anthropic.icon} ${PROVIDER_DISPLAY.anthropic.label}`,
      description: PROVIDER_DISPLAY.anthropic.description,
      detail: 'Recommended - Best coding performance'
    },
    {
      label: `${PROVIDER_DISPLAY.openai.icon} ${PROVIDER_DISPLAY.openai.label}`,
      description: PROVIDER_DISPLAY.openai.description,
      detail: 'Popular choice with strong capabilities'
    },
    {
      label: `${PROVIDER_DISPLAY.ollama.icon} ${PROVIDER_DISPLAY.ollama.label}`,
      description: PROVIDER_DISPLAY.ollama.description,
      detail: 'No API key required - runs on your machine'
    },
    {
      label: `${PROVIDER_DISPLAY.openrouter.icon} ${PROVIDER_DISPLAY.openrouter.label}`,
      description: PROVIDER_DISPLAY.openrouter.description,
      detail: 'Access 200+ models with one API key'
    },
    { label: '', kind: vscode.QuickPickItemKind.Separator },
    // Other providers
    {
      label: `${PROVIDER_DISPLAY.google.icon} ${PROVIDER_DISPLAY.google.label}`,
      description: PROVIDER_DISPLAY.google.description
    },
    {
      label: `${PROVIDER_DISPLAY.mistral.icon} ${PROVIDER_DISPLAY.mistral.label}`,
      description: PROVIDER_DISPLAY.mistral.description
    },
    {
      label: `${PROVIDER_DISPLAY.qwen.icon} ${PROVIDER_DISPLAY.qwen.label}`,
      description: PROVIDER_DISPLAY.qwen.description
    },
    {
      label: `${PROVIDER_DISPLAY.huggingface.icon} ${PROVIDER_DISPLAY.huggingface.label}`,
      description: PROVIDER_DISPLAY.huggingface.description
    },
    { label: '', kind: vscode.QuickPickItemKind.Separator },
    {
      label: `${PROVIDER_DISPLAY.custom.icon} ${PROVIDER_DISPLAY.custom.label}`,
      description: PROVIDER_DISPLAY.custom.description,
      detail: 'Enter custom URL and model name'
    }
  ];

  const selected = await vscode.window.showQuickPick(items, {
    title: 'Autonomi - Quick Start (1/3)',
    placeHolder: 'Select your AI provider',
    ignoreFocusOut: true
  });

  if (!selected) return undefined;

  // Map selection back to provider ID
  const label = selected.label;
  for (const [id, display] of Object.entries(PROVIDER_DISPLAY)) {
    if (label.includes(display.label)) {
      return id as ProviderId;
    }
  }

  return undefined;
}

/**
 * Step 2a: API Key Input
 */
async function showApiKeyInput(providerId: ProviderId): Promise<string | undefined> {
  const display = PROVIDER_DISPLAY[providerId];
  const definition = PROVIDER_REGISTRY[providerId];

  const keyUrls: Record<string, string> = {
    anthropic: 'https://console.anthropic.com/settings/keys',
    openai: 'https://platform.openai.com/api-keys',
    google: 'https://aistudio.google.com/apikey',
    mistral: 'https://console.mistral.ai/api-keys',
    qwen: 'https://dashscope.console.aliyun.com/apiKey',
    huggingface: 'https://huggingface.co/settings/tokens',
    openrouter: 'https://openrouter.ai/keys'
  };

  const keyUrl = keyUrls[providerId];

  // Show info message with link to get API key
  if (keyUrl) {
    const action = await vscode.window.showInformationMessage(
      `Get your ${display.label} API key`,
      'Open Console',
      'I have a key'
    );

    if (action === 'Open Console') {
      vscode.env.openExternal(vscode.Uri.parse(keyUrl));
    } else if (!action) {
      return undefined;
    }
  }

  const apiKey = await vscode.window.showInputBox({
    title: `Autonomi - ${display.label} API Key (2/3)`,
    prompt: `Enter your ${display.label} API key`,
    placeHolder: definition.id === 'anthropic' ? 'sk-ant-...' : 'sk-...',
    password: true,
    ignoreFocusOut: true,
    validateInput: (value) => {
      if (!value || value.trim().length < 10) {
        return 'Please enter a valid API key';
      }
      return undefined;
    }
  });

  return apiKey?.trim();
}

/**
 * Step 2b: Model Selection - Shows top 10 models
 */
async function showModelSelection(providerId: ProviderId): Promise<string | undefined> {
  const definition = PROVIDER_REGISTRY[providerId];
  const display = PROVIDER_DISPLAY[providerId];

  // Get top 10 models (sorted by tier - best first)
  const models = [...definition.models]
    .sort((a, b) => b.tier - a.tier)
    .slice(0, 10);

  const items: vscode.QuickPickItem[] = models.map((model, index) => {
    const tierLabels: Record<number, string> = {
      4: '$(star-full) Best',
      3: '$(star-half) Great',
      2: '$(star-empty) Good',
      1: '$(zap) Fast'
    };

    const costLabel = model.costPer1kInput === 0
      ? 'Free'
      : `$${(model.costPer1kInput * 1000).toFixed(2)}/1M in`;

    return {
      label: `${index === 0 ? '$(check) ' : ''}${model.name}`,
      description: tierLabels[model.tier] || '',
      detail: `${costLabel} | ${(model.contextWindow / 1000).toFixed(0)}K context | ${model.capabilities.slice(0, 3).join(', ')}`
    };
  });

  const selected = await vscode.window.showQuickPick(items, {
    title: `Autonomi - Select ${display.label} Model (3/3)`,
    placeHolder: 'Choose a model (first is recommended)',
    ignoreFocusOut: true
  });

  if (!selected) return undefined;

  // Find the model by name
  const model = models.find(m => selected.label.includes(m.name));
  return model?.id;
}

/**
 * Step 2c: Ollama Setup (no API key)
 */
async function showOllamaSetup(): Promise<{ baseUrl: string; modelId: string } | undefined> {
  // Check if Ollama is running
  const defaultUrl = 'http://localhost:11434/v1';

  const baseUrl = await vscode.window.showInputBox({
    title: 'Autonomi - Ollama Setup (2/3)',
    prompt: 'Ollama API URL (leave default if running locally)',
    value: defaultUrl,
    ignoreFocusOut: true
  });

  if (!baseUrl) return undefined;

  // Try to fetch available models from Ollama
  let availableModels: string[] = [];
  try {
    const response = await fetch(`${baseUrl.replace('/v1', '')}/api/tags`);
    if (response.ok) {
      const data = await response.json() as { models?: Array<{ name: string }> };
      availableModels = data.models?.map(m => m.name) || [];
    }
  } catch {
    // Ollama not running or not accessible
  }

  // Show model selection or input
  if (availableModels.length > 0) {
    const items: vscode.QuickPickItem[] = availableModels.slice(0, 10).map(name => ({
      label: name,
      description: 'Installed locally'
    }));

    items.push(
      { label: '', kind: vscode.QuickPickItemKind.Separator },
      { label: '$(add) Enter custom model name...', description: 'Pull a new model' }
    );

    const selected = await vscode.window.showQuickPick(items, {
      title: 'Autonomi - Select Ollama Model (3/3)',
      placeHolder: 'Choose an installed model',
      ignoreFocusOut: true
    });

    if (!selected) return undefined;

    if (selected.label.includes('custom')) {
      const modelId = await showCustomModelInput();
      if (!modelId) return undefined;
      return { baseUrl, modelId };
    }

    return { baseUrl, modelId: selected.label };
  } else {
    // No models found - show popular options
    const popularModels = [
      { label: 'llama3.2:latest', description: 'Meta Llama 3.2 - Great all-around' },
      { label: 'codellama:latest', description: 'Code Llama - Optimized for coding' },
      { label: 'deepseek-coder-v2:latest', description: 'DeepSeek Coder V2 - Strong coding' },
      { label: 'qwen2.5-coder:latest', description: 'Qwen 2.5 Coder - Fast coding' },
      { label: 'mistral:latest', description: 'Mistral 7B - Fast and capable' },
      { label: '', kind: vscode.QuickPickItemKind.Separator },
      { label: '$(add) Enter custom model name...', description: '' }
    ];

    const selected = await vscode.window.showQuickPick(popularModels, {
      title: 'Autonomi - Select Ollama Model (3/3)',
      placeHolder: 'Choose a model to use (will be pulled if not installed)',
      ignoreFocusOut: true
    });

    if (!selected) return undefined;

    if (selected.label.includes('custom')) {
      const modelId = await showCustomModelInput();
      if (!modelId) return undefined;
      return { baseUrl, modelId };
    }

    return { baseUrl, modelId: selected.label };
  }
}

/**
 * Step 2d: Custom Provider Setup
 */
async function showCustomProviderSetup(): Promise<{ baseUrl: string; apiKey: string; modelId: string } | undefined> {
  // Example URLs for reference
  const exampleUrls = [
    'http://localhost:11434/v1 (Ollama)',
    'http://localhost:1234/v1 (LM Studio)',
    'https://openrouter.ai/api/v1',
    'https://api.together.xyz/v1',
    'https://api.groq.com/openai/v1',
    'https://api.fireworks.ai/inference/v1'
  ];

  const baseUrl = await vscode.window.showInputBox({
    title: 'Autonomi - Custom Provider (2/4)',
    prompt: 'Enter the API base URL (OpenAI-compatible)',
    placeHolder: 'https://your-api.com/v1',
    ignoreFocusOut: true,
    validateInput: (value) => {
      if (!value || !value.startsWith('http')) {
        return 'Please enter a valid URL starting with http:// or https://';
      }
      return undefined;
    }
  });

  if (!baseUrl) return undefined;

  const apiKey = await vscode.window.showInputBox({
    title: 'Autonomi - Custom Provider (3/4)',
    prompt: 'Enter API key (leave empty if not required)',
    placeHolder: 'sk-...',
    password: true,
    ignoreFocusOut: true
  });

  if (apiKey === undefined) return undefined; // Cancelled

  const modelId = await vscode.window.showInputBox({
    title: 'Autonomi - Custom Provider (4/4)',
    prompt: 'Enter the model name/ID',
    placeHolder: 'e.g., gpt-4o, llama3.2, claude-3.5-sonnet',
    ignoreFocusOut: true,
    validateInput: (value) => {
      if (!value || value.trim().length < 2) {
        return 'Please enter a valid model name';
      }
      return undefined;
    }
  });

  if (!modelId) return undefined;

  return { baseUrl, apiKey: apiKey || '', modelId: modelId.trim() };
}

/**
 * Custom model name input
 */
async function showCustomModelInput(): Promise<string | undefined> {
  return vscode.window.showInputBox({
    title: 'Autonomi - Enter Model Name',
    prompt: 'Enter the model name/ID',
    placeHolder: 'e.g., llama3.2:latest, codellama:7b',
    ignoreFocusOut: true,
    validateInput: (value) => {
      if (!value || value.trim().length < 2) {
        return 'Please enter a valid model name';
      }
      return undefined;
    }
  });
}

/**
 * Save onboarding configuration
 */
async function saveOnboardingConfig(
  context: vscode.ExtensionContext,
  state: OnboardingState
): Promise<void> {
  if (!state.providerId) return;

  // Save API key to secret storage
  if (state.apiKey) {
    await context.secrets.store(`autonomi.apiKey.${state.providerId}`, state.apiKey);
  }

  // Save base URL if custom
  if (state.baseUrl) {
    await context.secrets.store(`autonomi.baseUrl.${state.providerId}`, state.baseUrl);
  }

  // Update VS Code settings
  const config = vscode.workspace.getConfiguration('autonomi');
  await config.update('provider.preferred', state.providerId, vscode.ConfigurationTarget.Global);

  if (state.modelId) {
    await config.update('provider.defaultModel', state.modelId, vscode.ConfigurationTarget.Global);
  }

  // Mark onboarding as complete
  await context.globalState.update('autonomi.onboardingComplete', true);
}

// Current onboarding version - bump this to force re-onboarding on updates
const ONBOARDING_VERSION = 2;

/**
 * Check if onboarding is needed
 */
export async function needsOnboarding(context: vscode.ExtensionContext): Promise<boolean> {
  // Check onboarding version - if changed, reset and show again
  const storedVersion = context.globalState.get<number>('autonomi.onboardingVersion', 0);
  if (storedVersion < ONBOARDING_VERSION) {
    // New onboarding version - reset completion status
    await context.globalState.update('autonomi.onboardingComplete', false);
    await context.globalState.update('autonomi.onboardingVersion', ONBOARDING_VERSION);
    return true;
  }

  // Check if onboarding was completed
  const completed = context.globalState.get<boolean>('autonomi.onboardingComplete', false);

  if (!completed) {
    return true; // Never completed onboarding
  }

  // Onboarding was completed - verify we still have a valid provider configured
  // Check if ANY provider has credentials (not just preferred)
  const providers = ['anthropic', 'openai', 'google', 'mistral', 'qwen', 'huggingface', 'openrouter'];
  for (const provider of providers) {
    const apiKey = await context.secrets.get(`autonomi.apiKey.${provider}`);
    if (apiKey) {
      return false; // Has at least one provider configured
    }
  }

  // Check ollama
  const ollamaUrl = await context.secrets.get('autonomi.baseUrl.ollama');
  if (ollamaUrl) {
    return false;
  }

  // Check custom
  const customUrl = await context.secrets.get('autonomi.baseUrl.custom');
  if (customUrl) {
    return false;
  }

  // No providers configured - need onboarding
  return true;
}

/**
 * Reset onboarding state (for testing/debugging)
 */
export async function resetOnboarding(context: vscode.ExtensionContext): Promise<void> {
  await context.globalState.update('autonomi.onboardingComplete', false);
  await context.globalState.update('autonomi.onboardingVersion', 0);
  vscode.window.showInformationMessage('Onboarding reset. Reload to see welcome screen.');
}

/**
 * Show welcome view in sidebar when no provider configured
 */
export function registerWelcomeView(context: vscode.ExtensionContext): vscode.Disposable {
  return vscode.window.registerWebviewViewProvider(
    'autonomi-welcome',
    {
      resolveWebviewView(webviewView) {
        webviewView.webview.options = { enableScripts: true };
        webviewView.webview.html = getWelcomeHtml();

        webviewView.webview.onDidReceiveMessage(async (message) => {
          if (message.command === 'startOnboarding') {
            vscode.commands.executeCommand('autonomi.quickStart');
          }
        });
      }
    }
  );
}

function getWelcomeHtml(): string {
  return `<!DOCTYPE html>
<html>
<head>
  <style>
    body {
      padding: 16px;
      font-family: var(--vscode-font-family);
      color: var(--vscode-foreground);
    }
    h2 {
      font-size: 16px;
      margin-bottom: 12px;
    }
    p {
      font-size: 13px;
      margin-bottom: 16px;
      opacity: 0.9;
    }
    button {
      background: var(--vscode-button-background);
      color: var(--vscode-button-foreground);
      border: none;
      padding: 8px 16px;
      cursor: pointer;
      font-size: 13px;
      width: 100%;
      border-radius: 2px;
    }
    button:hover {
      background: var(--vscode-button-hoverBackground);
    }
    .providers {
      margin-top: 16px;
      font-size: 12px;
      opacity: 0.7;
    }
  </style>
</head>
<body>
  <h2>Welcome to Autonomi</h2>
  <p>Multi-agent autonomous development platform. Configure your AI provider to get started.</p>
  <button onclick="start()">Quick Start</button>
  <div class="providers">
    Supports: Anthropic, OpenAI, Google, Mistral, Qwen, Ollama, HuggingFace, OpenRouter
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    function start() {
      vscode.postMessage({ command: 'startOnboarding' });
    }
  </script>
</body>
</html>`;
}
