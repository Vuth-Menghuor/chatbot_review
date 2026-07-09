import { canonicalizeBlockType } from './canonicalBlocks';

interface SerializeMessageBlockOptions {
  leadingNewline?: boolean;
  trailingNewline?: boolean;
}

export function stringifyBlockContent(content: unknown): string {
  return typeof content === 'string' ? content : JSON.stringify(content, null, 2);
}

export function serializeMessageBlock(
  type: string,
  content: unknown,
  options: SerializeMessageBlockOptions = {},
): string {
  const normalizedType = canonicalizeBlockType(type);
  const block = `---${normalizedType}\n${stringifyBlockContent(content)}\n---`;
  return `${options.leadingNewline ? '\n' : ''}${block}${options.trailingNewline ? '\n' : ''}`;
}
