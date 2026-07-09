import type { MessageBlock } from '~/types/message';

export interface MarkdownSection {
  type: 'html' | 'table' | 'chart';
  content?: string;
  tableBlock?: MessageBlock;
  chartBlock?: MessageBlock;
  key: string;
}

export function parseMarkdownSections(
  html: string,
  options: {
    blockId?: string | number;
    isComplete: boolean;
    onTableParseError?: (error: unknown) => void;
  },
): MarkdownSection[] {
  if (!html) return [];

  const sections: MarkdownSection[] = [];
  const regex =
    /<div class="custom-markdown-(table|chart)-placeholder" data-(?:table|chart)="([^"]+)"><\/div>/g;

  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let index = 0;

  while ((match = regex.exec(html)) !== null) {
    const tableIndex = match.index;

    if (tableIndex > lastIndex) {
      sections.push({
        type: 'html',
        content: html.substring(lastIndex, tableIndex),
        key: `html-${index++}`,
      });
    }

    try {
      const kind = match[1] || 'table';
      const decodedJson = decodeURIComponent(match[2] || '');
      const tableData = JSON.parse(decodedJson) as unknown;

      if (kind === 'chart') {
        sections.push({
          type: 'chart',
          chartBlock: {
            id: `${options.blockId || 'chart'}-inner-${index}`,
            type: 'chart',
            content: tableData,
            isComplete: options.isComplete,
          },
          key: `chart-${index++}`,
        });
      } else {
        sections.push({
          type: 'table',
          tableBlock: {
            id: `${options.blockId || 'table'}-inner-${index}`,
            type: 'table',
            content: tableData,
            isComplete: options.isComplete,
          },
          key: `table-${index++}`,
        });
      }
    } catch (error) {
      options.onTableParseError?.(error);
      sections.push({
        type: 'html',
        content: match[0],
        key: `html-${index++}`,
      });
    }

    lastIndex = regex.lastIndex;
  }

  if (lastIndex < html.length) {
    sections.push({
      type: 'html',
      content: html.substring(lastIndex),
      key: `html-${index++}`,
    });
  }

  return sections;
}
