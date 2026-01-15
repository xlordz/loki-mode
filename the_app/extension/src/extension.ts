/**
 * Autonomi VSCode Extension - Main Entry Point
 *
 * This is the main entry point for the Autonomi VSCode extension.
 * It handles activation and deactivation of the extension.
 */

import * as vscode from 'vscode';

let extension: any;
let outputChannel: vscode.OutputChannel;

/**
 * Activate the extension
 * Called when the extension is activated (e.g., when a command is executed)
 */
export async function activate(context: vscode.ExtensionContext): Promise<void> {
  console.log('Autonomi extension activating...');

  // Create output channel
  outputChannel = vscode.window.createOutputChannel('Autonomi');
  context.subscriptions.push(outputChannel);

  // Register ALL commands upfront so they're always available
  registerAllCommands(context);

  // Try to initialize the main extension
  try {
    const { AutonomiExtension } = await import('./autonomi-extension');
    extension = new AutonomiExtension(context);
    await extension.initialize();
    console.log('Autonomi extension initialized');
  } catch (error) {
    console.error('Failed to initialize Autonomi extension:', error);
    outputChannel.appendLine(`Init error: ${(error as Error).message}`);
    outputChannel.appendLine((error as Error).stack || '');
  }

  // Check if onboarding is needed
  try {
    const { needsOnboarding } = await import('./ui/onboarding');
    const needsSetup = await needsOnboarding(context);
    console.log('Autonomi: needsOnboarding =', needsSetup);

    if (needsSetup) {
      const action = await vscode.window.showInformationMessage(
        'Welcome to Autonomi! Set up your AI provider to start autonomous development.',
        { modal: true },
        'Quick Start',
        'Later'
      );

      if (action === 'Quick Start') {
        const { showOnboarding } = await import('./ui/onboarding');
        await showOnboarding(context);
      }
    }
  } catch (error) {
    console.error('Failed to check onboarding:', error);
  }

  console.log('Autonomi extension activated');
}

/**
 * Register all commands
 */
function registerAllCommands(context: vscode.ExtensionContext): void {
  const commands: Array<{ id: string; handler: () => void | Promise<void> }> = [
    // Quick Start / Onboarding
    {
      id: 'autonomi.quickStart',
      handler: async () => {
        try {
          const { showOnboarding } = await import('./ui/onboarding');
          await showOnboarding(context);
        } catch (err) {
          vscode.window.showErrorMessage(`Onboarding error: ${(err as Error).message}`);
        }
      }
    },
    // Start Task
    {
      id: 'autonomi.startTask',
      handler: async () => {
        if (extension) {
          const desc = await vscode.window.showInputBox({
            prompt: 'Enter task description',
            placeHolder: 'e.g., Add a login form to the homepage'
          });
          if (desc) {
            await extension.startTask(desc);
          }
        } else {
          vscode.window.showWarningMessage('Extension not fully initialized. Run Quick Start first.');
        }
      }
    },
    // Stop Task
    {
      id: 'autonomi.stopTask',
      handler: async () => {
        if (extension) {
          await extension.stopTask();
        } else {
          vscode.window.showInformationMessage('No task running');
        }
      }
    },
    // Approve Plan
    {
      id: 'autonomi.approvePlan',
      handler: async () => {
        if (extension) {
          await extension.approvePlan();
        }
      }
    },
    // Reject Plan
    {
      id: 'autonomi.rejectPlan',
      handler: async () => {
        if (extension) {
          await extension.rejectPlan();
        }
      }
    },
    // Show Output
    {
      id: 'autonomi.showOutput',
      handler: () => {
        outputChannel.show();
      }
    },
    // Configure API Keys
    {
      id: 'autonomi.configureApiKeys',
      handler: async () => {
        try {
          const { showOnboarding } = await import('./ui/onboarding');
          await showOnboarding(context);
        } catch (err) {
          vscode.window.showErrorMessage(`Error: ${(err as Error).message}`);
        }
      }
    },
    // Show Status
    {
      id: 'autonomi.showStatus',
      handler: () => {
        if (extension) {
          const state = extension.getState();
          outputChannel.clear();
          outputChannel.appendLine('=== Autonomi Status ===');
          outputChannel.appendLine(`Running: ${state.isRunning}`);
          outputChannel.appendLine(`Phase: ${state.phase || 'idle'}`);
          outputChannel.appendLine(`Session Cost: $${state.cost.sessionCost.toFixed(2)}`);
          outputChannel.appendLine(`Queue Size: ${state.queue.pending.length}`);
          outputChannel.show();
        } else {
          outputChannel.appendLine('Extension not initialized');
          outputChannel.show();
        }
      }
    },
    // Clear Queue
    {
      id: 'autonomi.clearQueue',
      handler: () => {
        vscode.window.showInformationMessage('Queue cleared');
      }
    },
    // Open Settings
    {
      id: 'autonomi.openSettings',
      handler: () => {
        vscode.commands.executeCommand('workbench.action.openSettings', 'autonomi');
      }
    },
    // Start (alias)
    {
      id: 'autonomi.start',
      handler: () => {
        vscode.commands.executeCommand('autonomi.startTask');
      }
    },
    // Stop (alias)
    {
      id: 'autonomi.stop',
      handler: () => {
        vscode.commands.executeCommand('autonomi.stopTask');
      }
    },
    // Plan
    {
      id: 'autonomi.plan',
      handler: async () => {
        vscode.window.showInformationMessage('Use "Start Task" to create a development plan');
      }
    },
    // Approve (alias)
    {
      id: 'autonomi.approve',
      handler: () => {
        vscode.commands.executeCommand('autonomi.approvePlan');
      }
    },
    // Configure (alias)
    {
      id: 'autonomi.configure',
      handler: () => {
        vscode.commands.executeCommand('autonomi.quickStart');
      }
    }
  ];

  for (const { id, handler } of commands) {
    context.subscriptions.push(
      vscode.commands.registerCommand(id, handler)
    );
  }

  console.log(`Registered ${commands.length} commands`);
}

/**
 * Deactivate the extension
 * Called when the extension is deactivated (e.g., when VS Code is closing)
 */
export function deactivate(): void {
  console.log('Autonomi extension deactivating...');

  if (extension) {
    extension.dispose();
    extension = undefined;
  }

  console.log('Autonomi extension deactivated');
}
