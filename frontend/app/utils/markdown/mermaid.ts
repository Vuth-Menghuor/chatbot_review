interface MermaidApi {
  initialize(options: Record<string, unknown>): void;
  run(options: { nodes: HTMLElement[]; suppressErrors?: boolean }): Promise<void> | void;
}

let mermaidModule: Promise<MermaidApi> | null = null;

export function loadMermaid(): Promise<MermaidApi> {
  if (!mermaidModule) {
    mermaidModule = new Function("return import('mermaid')")().then(
      (m: { default: MermaidApi }) => m.default,
    );
  }

  return mermaidModule;
}

export function areMermaidFencesExplicitlyClosed(src: string): boolean {
  const openRe = /```\s*mermaid\s*(?:\r?\n|$)/gi;
  let match: RegExpExecArray | null;

  while ((match = openRe.exec(src)) !== null) {
    const after = src.slice(match.index + match[0].length);
    if (!/(^|\r?\n)```[ \t]*(?:\r?\n|$)/.test(after)) {
      return false;
    }
  }

  return true;
}

export function hasMermaidFence(src: string): boolean {
  return /```\s*mermaid\s*(?:\r?\n|$)/i.test(src);
}

export function normalizeMermaidLLMOutput(src: string): string {
  return src
    .split(/\r?\n/)
    .map((line) =>
      line.replace(/;\s*(%%[^\n]*)?$/i, (_, comment: string | undefined) =>
        comment ? ` ${comment}` : '',
      ),
    )
    .join('\n');
}
