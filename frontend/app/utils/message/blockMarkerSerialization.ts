import type { MessageBlock } from '~/types/message';
import { serializeMessageBlock } from './messageBlocks';

export function serializeBlockForMarkerPipeline(block: MessageBlock): string {
  if (block.type === 'code' && typeof block.content === 'string') {
    const language =
      typeof block.meta?.language === 'string' && block.meta.language.trim()
        ? block.meta.language.trim()
        : 'text';

    return `\`\`\`${language}\n${block.content}\n\`\`\``;
  }

  return serializeMessageBlock(String(block.type), block.content);
}

export function blocksToMarkerText(blocks: MessageBlock[]): string {
  return blocks.map(serializeBlockForMarkerPipeline).filter(Boolean).join('\n\n');
}
