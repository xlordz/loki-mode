/**
 * Approval Manager (EXT-002)
 * Handles approval workflow for execution plans with enterprise-configurable gates
 */

import { Plan } from './plan-generator';
import { Task, ConfidenceCalculator, ConfidenceTier } from '../confidence/calculator';

export type ApprovalGateSetting = 'always' | 'never' | 'confidence';

export interface ApprovalGateConfig {
  productionDeploy: ApprovalGateSetting;
  databaseMigration: ApprovalGateSetting;
  securityChanges: ApprovalGateSetting;
  newDependencies: ApprovalGateSetting;
  fileDeletion: ApprovalGateSetting;
  costThreshold: number;  // Pause if task cost exceeds this amount (USD)
  confidenceThreshold: number;  // Auto-approve if confidence >= this (0-1)
}

export interface GateCheckResult {
  gate: keyof ApprovalGateConfig | 'cost';
  triggered: boolean;
  reason: string;
  severity: 'info' | 'warning' | 'critical';
  autoApprovable: boolean;
}

export interface PendingApproval {
  plan: Plan;
  requestedAt: Date;
  expiresAt: Date;
  gateResults: GateCheckResult[];
  requiredApprovers: string[];
  approvals: ApprovalRecord[];
  rejections: ApprovalRecord[];
  status: 'pending' | 'approved' | 'rejected' | 'expired';
}

export interface ApprovalRecord {
  approver: string;
  timestamp: Date;
  decision: 'approve' | 'reject';
  comment?: string;
}

export interface ApprovalRequest {
  planId: string;
  title: string;
  description: string;
  estimatedCost: number;
  affectedFiles: string[];
  gateResults: GateCheckResult[];
  timeout: number;  // ms until expiration
}

export type ApprovalCallback = (request: ApprovalRequest) => Promise<boolean>;

// Default gate configuration
const DEFAULT_GATE_CONFIG: ApprovalGateConfig = {
  productionDeploy: 'always',
  databaseMigration: 'always',
  securityChanges: 'confidence',
  newDependencies: 'confidence',
  fileDeletion: 'confidence',
  costThreshold: 5.0,  // $5
  confidenceThreshold: 0.9,
};

// Patterns for detecting gate-triggering content
const GATE_PATTERNS: Record<string, RegExp[]> = {
  productionDeploy: [
    /\b(deploy|release|production|prod|live)\b/i,
    /\b(publish|rollout|ship)\b/i,
  ],
  databaseMigration: [
    /\b(migration|migrate|schema|database|db)\b/i,
    /\b(alter|drop|create table|add column)\b/i,
  ],
  securityChanges: [
    /\b(auth|security|password|credential|secret)\b/i,
    /\b(permission|role|access|token|session)\b/i,
    /\b(encrypt|decrypt|hash|salt)\b/i,
  ],
  newDependencies: [
    /\b(package|dependency|npm|yarn|pip|cargo)\b/i,
    /\b(install|add|upgrade)\b/i,
  ],
  fileDeletion: [
    /\b(delete|remove|drop|rm)\b/i,
    /\b(cleanup|deprecate|archive)\b/i,
  ],
};

export class ApprovalManager {
  private pendingApprovals: Map<string, PendingApproval> = new Map();
  private approvalGates: ApprovalGateConfig;
  private confidenceCalculator: ConfidenceCalculator;
  private approvalCallback?: ApprovalCallback;
  private approvalTimeout: number = 300000;  // 5 minutes default

  constructor(gateConfig?: Partial<ApprovalGateConfig>) {
    this.approvalGates = { ...DEFAULT_GATE_CONFIG, ...gateConfig };
    this.confidenceCalculator = new ConfidenceCalculator();
  }

  /**
   * Set callback for approval requests (e.g., UI notification)
   */
  setApprovalCallback(callback: ApprovalCallback): void {
    this.approvalCallback = callback;
  }

  /**
   * Set approval timeout in milliseconds
   */
  setApprovalTimeout(timeout: number): void {
    this.approvalTimeout = timeout;
  }

  /**
   * Request approval for a plan
   */
  async requestApproval(plan: Plan): Promise<boolean> {
    // Check if auto-approval is possible
    const canAutoApprove = await this.autoApprove(plan);
    if (canAutoApprove) {
      plan.approved = true;
      plan.approvedAt = new Date();
      plan.approvedBy = 'auto-approval';
      return true;
    }

    // Create pending approval
    const task: Task = {
      id: plan.taskId,
      description: plan.taskDescription,
      files: plan.affectedFiles,
    };

    const gateResults = this.checkGates(task);
    const now = new Date();

    const pending: PendingApproval = {
      plan,
      requestedAt: now,
      expiresAt: new Date(now.getTime() + this.approvalTimeout),
      gateResults,
      requiredApprovers: this.determineRequiredApprovers(gateResults),
      approvals: [],
      rejections: [],
      status: 'pending',
    };

    this.pendingApprovals.set(plan.id, pending);

    // Request approval via callback if set
    if (this.approvalCallback) {
      const request: ApprovalRequest = {
        planId: plan.id,
        title: `Approval required: ${plan.taskDescription}`,
        description: this.formatApprovalDescription(plan, gateResults),
        estimatedCost: plan.estimatedCost.expectedCost,
        affectedFiles: plan.affectedFiles,
        gateResults,
        timeout: this.approvalTimeout,
      };

      try {
        const approved = await this.approvalCallback(request);
        if (approved) {
          return this.approve(plan.id, 'user');
        } else {
          this.reject(plan.id, 'user', 'User rejected the plan');
          return false;
        }
      } catch (error) {
        // Callback failed, leave as pending
        return false;
      }
    }

    return false;
  }

  /**
   * Check if plan can be auto-approved based on gates and confidence
   */
  async autoApprove(plan: Plan): Promise<boolean> {
    const task: Task = {
      id: plan.taskId,
      description: plan.taskDescription,
      files: plan.affectedFiles,
    };

    // Check confidence
    const confidence = this.confidenceCalculator.calculate(task);
    if (confidence.overall < this.approvalGates.confidenceThreshold) {
      return false;
    }

    // Check cost threshold
    if (plan.estimatedCost.expectedCost > this.approvalGates.costThreshold) {
      return false;
    }

    // Check gates
    const gateResults = this.checkGates(task);
    const blockingGates = gateResults.filter(g => g.triggered && !g.autoApprovable);

    if (blockingGates.length > 0) {
      return false;
    }

    return true;
  }

  /**
   * Check if task requires approval based on confidence
   */
  requiresApproval(task: Task, confidence: number): boolean {
    // Always require approval below confidence threshold
    if (confidence < this.approvalGates.confidenceThreshold) {
      return true;
    }

    // Check gates
    const gateResults = this.checkGates(task);
    return gateResults.some(g => g.triggered && !g.autoApprovable);
  }

  /**
   * Check all gates for a task
   */
  checkGates(task: Task): GateCheckResult[] {
    const results: GateCheckResult[] = [];
    const description = task.description || '';
    const files = task.files || [];
    const confidence = this.confidenceCalculator.calculate(task);

    // Check each gate
    for (const [gateName, patterns] of Object.entries(GATE_PATTERNS)) {
      const setting = this.approvalGates[gateName as keyof ApprovalGateConfig];
      if (typeof setting !== 'string') continue;

      const triggered = patterns.some(p => p.test(description)) ||
        this.checkFilePatterns(files, gateName);

      if (triggered) {
        results.push({
          gate: gateName as keyof ApprovalGateConfig,
          triggered: true,
          reason: this.getGateReason(gateName, description, files),
          severity: this.getGateSeverity(gateName),
          autoApprovable: this.isGateAutoApprovable(
            setting as ApprovalGateSetting,
            confidence.overall
          ),
        });
      }
    }

    // Check cost threshold
    // Note: This will be checked during requestApproval with actual cost

    return results;
  }

  /**
   * Approve a pending plan
   */
  approve(planId: string, approver: string, comment?: string): boolean {
    const pending = this.pendingApprovals.get(planId);
    if (!pending || pending.status !== 'pending') {
      return false;
    }

    pending.approvals.push({
      approver,
      timestamp: new Date(),
      decision: 'approve',
      comment,
    });

    // Check if we have enough approvals
    const requiredCount = pending.requiredApprovers.length;
    if (pending.approvals.length >= Math.max(1, requiredCount)) {
      pending.status = 'approved';
      pending.plan.approved = true;
      pending.plan.approvedAt = new Date();
      pending.plan.approvedBy = approver;
      return true;
    }

    return false;
  }

  /**
   * Reject a pending plan
   */
  reject(planId: string, rejector: string, reason?: string): boolean {
    const pending = this.pendingApprovals.get(planId);
    if (!pending || pending.status !== 'pending') {
      return false;
    }

    pending.rejections.push({
      approver: rejector,
      timestamp: new Date(),
      decision: 'reject',
      comment: reason,
    });

    pending.status = 'rejected';
    return true;
  }

  /**
   * Get pending approval by plan ID
   */
  getPendingApproval(planId: string): PendingApproval | null {
    return this.pendingApprovals.get(planId) || null;
  }

  /**
   * Get all pending approvals
   */
  getAllPendingApprovals(): PendingApproval[] {
    return Array.from(this.pendingApprovals.values())
      .filter(p => p.status === 'pending');
  }

  /**
   * Clean up expired approvals
   */
  cleanupExpired(): number {
    const now = new Date();
    let cleaned = 0;

    for (const [id, pending] of this.pendingApprovals) {
      if (pending.status === 'pending' && pending.expiresAt < now) {
        pending.status = 'expired';
        cleaned++;
      }
    }

    return cleaned;
  }

  /**
   * Update gate configuration
   */
  updateGateConfig(config: Partial<ApprovalGateConfig>): void {
    this.approvalGates = { ...this.approvalGates, ...config };
  }

  /**
   * Get current gate configuration
   */
  getGateConfig(): ApprovalGateConfig {
    return { ...this.approvalGates };
  }

  /**
   * Check if files match gate patterns
   */
  private checkFilePatterns(files: string[], gateName: string): boolean {
    const filePatterns: Record<string, RegExp[]> = {
      productionDeploy: [/deploy/, /\.prod\./, /production/],
      databaseMigration: [/migration/, /\.sql$/, /schema/],
      securityChanges: [/auth/, /security/, /\.secret/, /\.key$/],
      newDependencies: [/package\.json$/, /requirements\.txt$/, /Cargo\.toml$/],
      fileDeletion: [],  // Handled by task description
    };

    const patterns = filePatterns[gateName] || [];
    return files.some(f => patterns.some(p => p.test(f)));
  }

  /**
   * Get human-readable reason for gate trigger
   */
  private getGateReason(gateName: string, description: string, files: string[]): string {
    const reasons: Record<string, string> = {
      productionDeploy: 'Task involves deployment to production environment',
      databaseMigration: 'Task involves database schema changes',
      securityChanges: 'Task modifies security-related code',
      newDependencies: 'Task adds or modifies dependencies',
      fileDeletion: 'Task involves deleting files',
    };
    return reasons[gateName] || `Gate ${gateName} triggered`;
  }

  /**
   * Get severity level for a gate
   */
  private getGateSeverity(gateName: string): 'info' | 'warning' | 'critical' {
    const severities: Record<string, 'info' | 'warning' | 'critical'> = {
      productionDeploy: 'critical',
      databaseMigration: 'critical',
      securityChanges: 'critical',
      newDependencies: 'warning',
      fileDeletion: 'warning',
    };
    return severities[gateName] || 'info';
  }

  /**
   * Check if gate can be auto-approved based on setting and confidence
   */
  private isGateAutoApprovable(setting: ApprovalGateSetting, confidence: number): boolean {
    switch (setting) {
      case 'always':
        return false;  // Always requires manual approval
      case 'never':
        return true;   // Never requires approval (dangerous!)
      case 'confidence':
        return confidence >= this.approvalGates.confidenceThreshold;
      default:
        return false;
    }
  }

  /**
   * Determine required approvers based on gate results
   */
  private determineRequiredApprovers(gateResults: GateCheckResult[]): string[] {
    const approvers: string[] = [];

    for (const result of gateResults) {
      if (result.triggered && !result.autoApprovable) {
        switch (result.severity) {
          case 'critical':
            approvers.push('lead', 'security');
            break;
          case 'warning':
            approvers.push('reviewer');
            break;
          default:
            approvers.push('any');
        }
      }
    }

    return [...new Set(approvers)];
  }

  /**
   * Format description for approval request
   */
  private formatApprovalDescription(plan: Plan, gateResults: GateCheckResult[]): string {
    const lines: string[] = [
      `Task: ${plan.taskDescription}`,
      '',
      `Estimated Cost: $${plan.estimatedCost.expectedCost.toFixed(4)}`,
      `Affected Files: ${plan.affectedFiles.length}`,
      '',
      'Gates Triggered:',
    ];

    for (const result of gateResults) {
      if (result.triggered) {
        lines.push(`  - [${result.severity.toUpperCase()}] ${result.gate}: ${result.reason}`);
      }
    }

    if (gateResults.filter(g => g.triggered).length === 0) {
      lines.push('  - None');
    }

    return lines.join('\n');
  }
}
