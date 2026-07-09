import type { MessageBlock, MessageBlockType } from '~/types/message';
import { tryParseJsonLike } from '../json';
import { canonicalizeBlock } from './canonicalBlocks';
import { legacyToolContentToMarkdown } from '../tool/formulaToMarkdown';
import { chartToolRequestToBlockContent } from '../tool/chartToolRequestPreview';

function tryParsePredictionString(text: string): Record<string, unknown> | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) return null;

  const parsed = tryParseJsonLike(trimmed);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;

  const obj = parsed as Record<string, unknown>;
  const firstItem =
    Array.isArray(obj.items) && obj.items.length > 0 ? obj.items[0] : undefined;

  if (
    'hsCode' in obj ||
    (firstItem && typeof firstItem === 'object' && 'hsCode' in firstItem)
  ) {
    return obj;
  }

  return null;
}

function isMermaidFenceLanguage(language: string): boolean {
  const langKey = language.trim().split(/\s+/)[0]?.toLowerCase() ?? '';
  return langKey === 'mermaid' || langKey === 'mmd';
}

export function normalizeRawTextBlocks(rawText: string): MessageBlock[] {
  if (!rawText) return [];

  const predictionObj = tryParsePredictionString(rawText);
  if (predictionObj) {
    return [
      {
        id: 'b-prediction-auto',
        type: 'prediction',
        content: predictionObj,
        isComplete: true,
      },
    ];
  }

  const blocks: MessageBlock[] = [];
  const lines = rawText.split('\n');
  let seq = 0;
  let currentMarkdown = '';
  let i = 0;

  const flushMarkdown = () => {
    if (!currentMarkdown.trim()) return;
    blocks.push({
      id: `b${seq++}`,
      type: 'markdown',
      content: currentMarkdown.trim(),
      isComplete: true,
    });
    currentMarkdown = '';
  };

  while (i < lines.length) {
    const line = lines[i];
    if (line === undefined) {
      i++;
      continue;
    }

    if (line.startsWith('---') && line.length > 3 && !line.startsWith('----')) {
      const rawType = line.substring(3).trim().toLowerCase();
      flushMarkdown();

      let contentStr = '';
      i++;

      while (i < lines.length) {
        const currentLine = lines[i];
        if (currentLine === undefined || currentLine.startsWith('---')) break;
        contentStr += `${currentLine}\n`;
        i++;
      }

      const markerLine = lines[i];
      const isComplete = markerLine !== undefined && markerLine.startsWith('---');
      i++;

      const parsedContent = tryParseJsonLike(contentStr.trim());
      const legacyMarkdown = legacyToolContentToMarkdown(rawType, parsedContent ?? contentStr.trim());
      if (legacyMarkdown) {
        blocks.push({
          id: `b${seq++}`,
          type: 'markdown',
          content: legacyMarkdown,
          isComplete,
        });
        continue;
      }

      const canonical = canonicalizeBlock({ type: rawType });

      blocks.push({
        id: `b${seq++}`,
        type: canonical.type as MessageBlockType,
        content: parsedContent,
        meta: canonical.meta,
        isComplete,
      });
      continue;
    }

    if (line.startsWith('```')) {
      flushMarkdown();
      const language = line.substring(3).trim();
      let contentStr = '';
      i++;

      while (i < lines.length) {
        const currentLine = lines[i];
        if (currentLine === undefined || currentLine.startsWith('```')) break;
        contentStr += `${currentLine}\n`;
        i++;
      }

      const markerLine = lines[i];
      const isComplete = markerLine !== undefined && markerLine.startsWith('```');
      i++;

      const trimmedContent = contentStr.trim();
      const parsedJson = language === 'json' || !language ? tryParseJsonLike(trimmedContent) : null;
      const parsedPrediction =
        language === 'json' || !language ? tryParsePredictionString(trimmedContent) : null;
      const chartPreview =
        parsedJson && typeof parsedJson === 'object'
          ? chartToolRequestToBlockContent(parsedJson)
          : null;

      if (chartPreview) {
        blocks.push({
          id: `b${seq++}`,
          type: 'chart',
          content: chartPreview,
          isComplete: true,
        });
      } else if (parsedPrediction) {
        blocks.push({
          id: `b${seq++}`,
          type: 'prediction',
          content: parsedPrediction,
          isComplete,
        });
      } else if (isMermaidFenceLanguage(language)) {
        blocks.push({
          id: `b${seq++}`,
          type: 'markdown',
          content: `\`\`\`mermaid\n${trimmedContent}\n\`\`\``,
          isComplete,
        });
      } else {
        blocks.push({
          id: `b${seq++}`,
          type: 'code',
          content: trimmedContent,
          meta: { language: language || 'code' },
          isComplete,
        });
      }
      continue;
    }

    currentMarkdown += `${line}\n`;
    i++;
  }

  flushMarkdown();

  const lastBlock = blocks[blocks.length - 1];
  if (lastBlock && lastBlock.type === 'markdown') {
    lastBlock.isComplete = false;
  }

  return blocks;
}
