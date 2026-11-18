import * as vscode from 'vscode';

import { RewindCli, RewindCliError } from './cli';
import { formatDiffDocument } from './diffFormat';
import { confirmAndRewind, previewRewind } from './rewindActions';
import { loadSessionNodes, loadStepNodes, RewindNode, SessionNode, StepNode } from './timelineModel';

/** Wired to `vscode.window.showErrorMessage` everywhere this file passes a `showError` seam down into
 * the vscode-free modules (`rewindActions.ts`, `timelineModel.ts`), so a `RewindCliError` -- the CLI's
 * own `rewindagents-error` payload -- reaches the user as one message, never an unhandled rejection. */
function showError(message: string): void {
  void vscode.window.showErrorMessage(message);
}

const DIFF_SCHEME = 'rewindagents-diff';

function cliPathFromConfig(): string {
  return vscode.workspace.getConfiguration('rewindagents').get<string>('cliPath', 'rewindagents');
}

function workspaceCwd(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

function makeCli(): RewindCli {
  return new RewindCli({ cliPath: cliPathFromConfig(), cwd: workspaceCwd() });
}

class RewindTimelineProvider implements vscode.TreeDataProvider<RewindNode> {
  private readonly emitter = new vscode.EventEmitter<RewindNode | undefined | void>();
  readonly onDidChangeTreeData = this.emitter.event;

  constructor(private readonly cli: RewindCli) {}

  refresh(): void {
    this.emitter.fire();
  }

  getTreeItem(element: RewindNode): vscode.TreeItem {
    if (element.kind === 'session') {
      const item = new vscode.TreeItem(element.label, vscode.TreeItemCollapsibleState.Collapsed);
      item.description = element.description;
      item.contextValue = 'rewindSession';
      return item;
    }
    const item = new vscode.TreeItem(element.label, vscode.TreeItemCollapsibleState.None);
    item.description = element.description;
    item.contextValue = 'rewindStep';
    item.command = {
      command: 'rewindagents.openStepDiff',
      title: 'Open Diff',
      arguments: [element],
    };
    return item;
  }

  async getChildren(element?: RewindNode): Promise<RewindNode[]> {
    if (!element) {
      return loadSessionNodes(this.cli, showError);
    }
    if (element.kind === 'session') {
      return loadStepNodes(this.cli, element.session, showError);
    }
    return [];
  }
}

class DiffContentProvider implements vscode.TextDocumentContentProvider {
  constructor(private readonly cli: RewindCli) {}

  async provideTextDocumentContent(uri: vscode.Uri): Promise<string> {
    const params = new URLSearchParams(uri.query);
    const session = params.get('session') ?? undefined;
    const step = Number(params.get('step'));
    const path = params.get('path') ?? undefined;
    try {
      const diff = await this.cli.diff(step, session);
      return formatDiffDocument(diff, path);
    } catch (e) {
      // A readonly document provider has no modal or status bar of its own to raise a popup from;
      // the error becomes the document's own content, so the user still sees exactly what the CLI
      // said (RewindCliError carries its `error` field verbatim) instead of a thrown rejection VS
      // Code would otherwise show as a generic "cannot open" dialog with no message in it.
      const message = e instanceof RewindCliError ? e.message : (e as Error).message;
      return `rewindagents could not load this diff: ${message}`;
    }
  }
}

function diffUriFor(step: StepNode): vscode.Uri {
  const params = new URLSearchParams();
  params.set('session', step.session);
  params.set('step', String(step.seq));
  return vscode.Uri.parse(`${DIFF_SCHEME}:/step-${step.session}-${step.seq}.diff?${params.toString()}`);
}

async function promptForStep(): Promise<number | undefined> {
  const value = await vscode.window.showInputBox({ prompt: 'Rewind to step number' });
  if (value === undefined) {
    return undefined;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function isStepNode(value: unknown): value is StepNode {
  return !!value && typeof value === 'object' && (value as SessionNode | StepNode).kind === 'step';
}

export function activate(context: vscode.ExtensionContext): void {
  const cli = makeCli();
  const provider = new RewindTimelineProvider(cli);
  const diffProvider = new DiffContentProvider(cli);

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('rewindagentsTimeline', provider),
    vscode.workspace.registerTextDocumentContentProvider(DIFF_SCHEME, diffProvider),

    vscode.commands.registerCommand('rewindagents.refresh', () => provider.refresh()),

    vscode.commands.registerCommand('rewindagents.openStepDiff', async (step: StepNode) => {
      const uri = diffUriFor(step);
      const doc = await vscode.workspace.openTextDocument(uri);
      await vscode.window.showTextDocument(doc, { preview: true });
    }),

    vscode.commands.registerCommand('rewindagents.previewRewind', async (arg?: unknown) => {
      const step = isStepNode(arg) ? arg : undefined;
      const to = step ? step.seq : await promptForStep();
      if (to === undefined) {
        return;
      }
      // previewRewind already catches RewindCliError itself (showing it via `showError`
      // below) and returns undefined in that case -- nothing further to render then.
      const result = await previewRewind(cli, to, step?.session, showError);
      if (!result) {
        return;
      }
      if (result.refused) {
        void vscode.window.showWarningMessage(result.message);
      } else {
        void vscode.window.showInformationMessage(result.message);
      }
    }),

    vscode.commands.registerCommand('rewindagents.rewindToHere', async (arg?: unknown) => {
      const step = isStepNode(arg) ? arg : undefined;
      const to = step ? step.seq : await promptForStep();
      if (to === undefined) {
        return;
      }
      const outcome = await confirmAndRewind(cli, to, step?.session, async (message) => {
        const choice = await vscode.window.showWarningMessage(message, { modal: true }, 'Rewind');
        return choice === 'Rewind';
      });
      if (outcome.cancelled) {
        return;
      }
      if (outcome.refused) {
        void vscode.window.showWarningMessage(outcome.message);
      } else {
        void vscode.window.showInformationMessage(`Rewound to step ${to}.`);
        provider.refresh();
      }
    }),
  );
}

export function deactivate(): void {
  // Nothing to tear down: the CLI adapter holds no open handles between calls.
}
