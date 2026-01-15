/**
 * Plan Generator (EXT-002)
 * Generates execution plans for tasks with cost estimation
 */

import { Task, ConfidenceCalculator, ConfidenceTier } from '../confidence/calculator';
import { calculateCost, estimateCostRange, formatCost } from '../cost/pricing';

export type AgentType =
  | 'architect'
  | 'developer'
  | 'tester'
  | 'reviewer'
  | 'deployer'
  | 'documenter'
  | 'security'
  | 'performance';

export interface PlanStep {
  index: number;
  description: string;
  agentType: AgentType;
  files: string[];
  estimatedTokens: number;
  estimatedCost: number;
  dependencies: number[];  // Indices of steps this depends on
  parallel: boolean;       // Can run in parallel with other steps
}

export interface CostEstimate {
  minCost: number;
  maxCost: number;
  expectedCost: number;
  breakdown: {
    agentType: AgentType;
    estimatedTokens: number;
    estimatedCost: number;
  }[];
  confidence: number;
}

export interface Plan {
  id: string;
  taskId: string;
  taskDescription: string;
  steps: PlanStep[];
  affectedFiles: string[];
  estimatedCost: CostEstimate;
  approved: boolean;
  approvedAt?: Date;
  approvedBy?: string;
  createdAt: Date;
  executionOrder: number[][];  // Parallel groups of step indices
  estimatedDuration: number;   // In milliseconds
}

// Token estimates per agent type (input + output)
const AGENT_TOKEN_ESTIMATES: Record<AgentType, { base: number; perFile: number }> = {
  architect: { base: 5000, perFile: 500 },
  developer: { base: 3000, perFile: 1000 },
  tester: { base: 2000, perFile: 800 },
  reviewer: { base: 1500, perFile: 400 },
  deployer: { base: 1000, perFile: 200 },
  documenter: { base: 1500, perFile: 300 },
  security: { base: 2500, perFile: 600 },
  performance: { base: 2000, perFile: 500 },
};

// Model tier by agent type
const AGENT_MODEL_TIER: Record<AgentType, 'fast' | 'balanced' | 'powerful'> = {
  architect: 'powerful',
  developer: 'balanced',
  tester: 'fast',
  reviewer: 'balanced',
  deployer: 'fast',
  documenter: 'fast',
  security: 'balanced',
  performance: 'balanced',
};

export interface PlanGeneratorConfig {
  defaultModel?: string;
  maxSteps?: number;
  includeTests?: boolean;
  includeReview?: boolean;
  includeSecurity?: boolean;
}

export class PlanGenerator {
  private confidenceCalculator: ConfidenceCalculator;
  private config: PlanGeneratorConfig;

  constructor(config?: PlanGeneratorConfig) {
    this.confidenceCalculator = new ConfidenceCalculator();
    this.config = {
      defaultModel: 'claude-sonnet-4-5',
      maxSteps: 20,
      includeTests: true,
      includeReview: true,
      includeSecurity: true,
      ...config,
    };
  }

  /**
   * Generate a plan for a task
   */
  async generatePlan(task: Task): Promise<Plan> {
    const planId = this.generatePlanId();
    const affectedFiles = await this.identifyAffectedFiles(task);
    const confidence = this.confidenceCalculator.calculate(task);
    const steps = this.generateSteps(task, affectedFiles, confidence.tier);
    const executionOrder = this.calculateExecutionOrder(steps);
    const estimatedCost = await this.estimateCost({ steps } as Plan);

    return {
      id: planId,
      taskId: task.id,
      taskDescription: task.description,
      steps,
      affectedFiles,
      estimatedCost,
      approved: false,
      createdAt: new Date(),
      executionOrder,
      estimatedDuration: this.estimateDuration(steps),
    };
  }

  /**
   * Identify files that will be affected by the task
   */
  async identifyAffectedFiles(task: Task): Promise<string[]> {
    const files: Set<string> = new Set();

    // Start with explicitly mentioned files
    if (task.files) {
      task.files.forEach(f => files.add(f));
    }

    // Parse description for file patterns
    const description = task.description || '';

    // Match file paths
    const filePatterns = [
      /(?:^|\s)([a-zA-Z0-9_\-/.]+\.[a-zA-Z0-9]+)(?:\s|$|,|;)/g,
      /['"`]([^'"`]+\.[a-zA-Z0-9]+)['"`]/g,
    ];

    for (const pattern of filePatterns) {
      let match;
      while ((match = pattern.exec(description)) !== null) {
        const potentialFile = match[1];
        // Basic validation that it looks like a file
        if (potentialFile.includes('.') && !potentialFile.startsWith('http')) {
          files.add(potentialFile);
        }
      }
    }

    // Infer related files based on task type
    if (task.type) {
      const inferredFiles = this.inferRelatedFiles(task.type, Array.from(files));
      inferredFiles.forEach(f => files.add(f));
    }

    return Array.from(files);
  }

  /**
   * Estimate cost for a plan
   */
  async estimateCost(plan: Plan): Promise<CostEstimate> {
    const breakdown: CostEstimate['breakdown'] = [];
    let totalMinCost = 0;
    let totalMaxCost = 0;
    let totalExpectedCost = 0;

    for (const step of plan.steps) {
      const tier = AGENT_MODEL_TIER[step.agentType];
      // Assume 60% input, 40% output for estimation
      const inputTokens = Math.floor(step.estimatedTokens * 0.6);
      const outputTokens = Math.floor(step.estimatedTokens * 0.4);

      const costRange = estimateCostRange(inputTokens, outputTokens, tier);

      breakdown.push({
        agentType: step.agentType,
        estimatedTokens: step.estimatedTokens,
        estimatedCost: costRange.typical,
      });

      totalMinCost += costRange.min;
      totalMaxCost += costRange.max;
      totalExpectedCost += costRange.typical;
    }

    // Add some uncertainty buffer
    const uncertaintyBuffer = 1.2;
    totalMaxCost *= uncertaintyBuffer;

    // Calculate confidence based on number of assumptions made
    const assumptionCount = plan.steps.filter(s => s.files.length === 0).length;
    const confidence = Math.max(0.5, 1 - (assumptionCount * 0.1));

    return {
      minCost: totalMinCost,
      maxCost: totalMaxCost,
      expectedCost: totalExpectedCost,
      breakdown,
      confidence,
    };
  }

  /**
   * Generate execution steps for the task
   */
  private generateSteps(
    task: Task,
    affectedFiles: string[],
    confidenceTier: ConfidenceTier
  ): PlanStep[] {
    const steps: PlanStep[] = [];
    let stepIndex = 0;

    // Architecture/planning step for complex tasks
    if (confidenceTier === ConfidenceTier.TIER_3 || confidenceTier === ConfidenceTier.TIER_4) {
      steps.push(this.createStep(stepIndex++, {
        description: 'Analyze requirements and design solution architecture',
        agentType: 'architect',
        files: affectedFiles,
        dependencies: [],
        parallel: false,
      }));
    }

    // Main development step
    steps.push(this.createStep(stepIndex++, {
      description: `Implement changes: ${task.description}`,
      agentType: 'developer',
      files: affectedFiles,
      dependencies: steps.length > 0 ? [0] : [],
      parallel: false,
    }));

    // Testing step
    if (this.config.includeTests) {
      const testFiles = affectedFiles
        .filter(f => !f.includes('.test.') && !f.includes('.spec.'))
        .map(f => this.inferTestFile(f));

      steps.push(this.createStep(stepIndex++, {
        description: 'Write and run tests for changes',
        agentType: 'tester',
        files: testFiles,
        dependencies: [stepIndex - 2],
        parallel: false,
      }));
    }

    // Security review for sensitive changes
    if (this.config.includeSecurity && this.needsSecurityReview(task)) {
      steps.push(this.createStep(stepIndex++, {
        description: 'Security review of changes',
        agentType: 'security',
        files: affectedFiles,
        dependencies: [stepIndex - 2],
        parallel: true,
      }));
    }

    // Code review step
    if (this.config.includeReview) {
      steps.push(this.createStep(stepIndex++, {
        description: 'Code review and quality checks',
        agentType: 'reviewer',
        files: affectedFiles,
        dependencies: this.config.includeTests ? [stepIndex - 3, stepIndex - 2] : [stepIndex - 2],
        parallel: !!(this.config.includeSecurity && this.needsSecurityReview(task)),
      }));
    }

    // Documentation update if needed
    if (this.needsDocumentation(task)) {
      steps.push(this.createStep(stepIndex++, {
        description: 'Update documentation',
        agentType: 'documenter',
        files: this.inferDocFiles(affectedFiles),
        dependencies: [stepIndex - 2],
        parallel: false,
      }));
    }

    return steps;
  }

  /**
   * Create a plan step with token/cost estimation
   */
  private createStep(
    index: number,
    config: {
      description: string;
      agentType: AgentType;
      files: string[];
      dependencies: number[];
      parallel: boolean;
    }
  ): PlanStep {
    const tokenEstimate = AGENT_TOKEN_ESTIMATES[config.agentType];
    const estimatedTokens = tokenEstimate.base + (config.files.length * tokenEstimate.perFile);

    const tier = AGENT_MODEL_TIER[config.agentType];
    const inputTokens = Math.floor(estimatedTokens * 0.6);
    const outputTokens = Math.floor(estimatedTokens * 0.4);
    const costRange = estimateCostRange(inputTokens, outputTokens, tier);

    return {
      index,
      description: config.description,
      agentType: config.agentType,
      files: config.files,
      estimatedTokens,
      estimatedCost: costRange.typical,
      dependencies: config.dependencies,
      parallel: config.parallel,
    };
  }

  /**
   * Calculate optimal execution order with parallel groups
   */
  private calculateExecutionOrder(steps: PlanStep[]): number[][] {
    const order: number[][] = [];
    const completed = new Set<number>();

    while (completed.size < steps.length) {
      const currentGroup: number[] = [];

      for (const step of steps) {
        if (completed.has(step.index)) continue;

        // Check if all dependencies are completed
        const depsCompleted = step.dependencies.every(d => completed.has(d));
        if (depsCompleted) {
          currentGroup.push(step.index);
        }
      }

      if (currentGroup.length === 0) {
        // Circular dependency or error - add remaining steps sequentially
        for (const step of steps) {
          if (!completed.has(step.index)) {
            order.push([step.index]);
            completed.add(step.index);
          }
        }
        break;
      }

      // Group parallel steps together
      const parallelSteps = currentGroup.filter(i => steps[i].parallel);
      const sequentialSteps = currentGroup.filter(i => !steps[i].parallel);

      // Add sequential steps first, then parallel group
      for (const idx of sequentialSteps) {
        order.push([idx]);
        completed.add(idx);
      }

      if (parallelSteps.length > 0) {
        order.push(parallelSteps);
        parallelSteps.forEach(idx => completed.add(idx));
      }
    }

    return order;
  }

  /**
   * Estimate total duration in milliseconds
   */
  private estimateDuration(steps: PlanStep[]): number {
    // Rough estimates: 1 token takes about 20ms to process on average
    const msPerToken = 20;
    const totalTokens = steps.reduce((sum, s) => sum + s.estimatedTokens, 0);

    // Account for some parallelization benefit
    const parallelSteps = steps.filter(s => s.parallel).length;
    const parallelizationFactor = 1 - (parallelSteps / steps.length * 0.3);

    return Math.round(totalTokens * msPerToken * parallelizationFactor);
  }

  /**
   * Infer related files based on task type
   */
  private inferRelatedFiles(taskType: string, existingFiles: string[]): string[] {
    const inferred: string[] = [];

    switch (taskType) {
      case 'test':
        existingFiles.forEach(f => {
          if (!f.includes('.test.') && !f.includes('.spec.')) {
            inferred.push(this.inferTestFile(f));
          }
        });
        break;
      case 'feature':
        // Might need to add index files, types, etc.
        break;
      case 'documentation':
        inferred.push('README.md');
        break;
    }

    return inferred;
  }

  /**
   * Infer test file path from source file
   */
  private inferTestFile(sourceFile: string): string {
    const ext = sourceFile.split('.').pop() || 'ts';
    const baseName = sourceFile.replace(`.${ext}`, '');
    return `${baseName}.test.${ext}`;
  }

  /**
   * Infer documentation files
   */
  private inferDocFiles(affectedFiles: string[]): string[] {
    const docs: string[] = ['README.md'];

    // Add related doc files
    for (const file of affectedFiles) {
      if (file.includes('/api/')) {
        docs.push('docs/api.md');
      }
    }

    return [...new Set(docs)];
  }

  /**
   * Check if task needs security review
   */
  private needsSecurityReview(task: Task): boolean {
    const securityPatterns = [
      /\b(auth|security|password|credential|token|secret|encrypt|permission)\b/i,
      /\b(login|logout|session|cookie|jwt)\b/i,
      /\b(sql|injection|xss|csrf|sanitize)\b/i,
    ];

    const description = task.description || '';
    return securityPatterns.some(p => p.test(description));
  }

  /**
   * Check if task needs documentation update
   */
  private needsDocumentation(task: Task): boolean {
    const docPatterns = [
      /\b(api|endpoint|interface|public)\b/i,
      /\b(breaking|major|new feature)\b/i,
      /\b(config|configuration|setting)\b/i,
    ];

    const description = task.description || '';
    return docPatterns.some(p => p.test(description));
  }

  /**
   * Generate unique plan ID
   */
  private generatePlanId(): string {
    return `plan_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Format plan as human-readable summary
   */
  formatPlanSummary(plan: Plan): string {
    const lines: string[] = [
      `Plan: ${plan.id}`,
      `Task: ${plan.taskDescription}`,
      ``,
      `Affected Files (${plan.affectedFiles.length}):`,
      ...plan.affectedFiles.map(f => `  - ${f}`),
      ``,
      `Execution Steps (${plan.steps.length}):`,
    ];

    for (const step of plan.steps) {
      lines.push(`  ${step.index + 1}. [${step.agentType}] ${step.description}`);
      lines.push(`     Files: ${step.files.length}, Est. Tokens: ${step.estimatedTokens}, Est. Cost: ${formatCost(step.estimatedCost)}`);
    }

    lines.push(``);
    lines.push(`Cost Estimate:`);
    lines.push(`  Min: ${formatCost(plan.estimatedCost.minCost)}`);
    lines.push(`  Expected: ${formatCost(plan.estimatedCost.expectedCost)}`);
    lines.push(`  Max: ${formatCost(plan.estimatedCost.maxCost)}`);
    lines.push(`  Confidence: ${(plan.estimatedCost.confidence * 100).toFixed(0)}%`);
    lines.push(``);
    lines.push(`Estimated Duration: ${Math.round(plan.estimatedDuration / 1000)}s`);
    lines.push(`Status: ${plan.approved ? 'Approved' : 'Pending Approval'}`);

    return lines.join('\n');
  }
}
