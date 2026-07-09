import { bundledLanguages, createHighlighter, type BundledLanguage, type Highlighter } from 'shiki';
import { languageAliasNames, languageNames } from '@shikijs/langs';
import lightPlus from '@shikijs/themes/light-plus';
import darkPlus from '@shikijs/themes/dark-plus';

let highlighter: Highlighter | null = null;
let highlighterPromise: Promise<Highlighter> | null = null;

const LANGUAGE_ALIASES: Record<string, BundledLanguage> = {
  bat: 'batch',
  cmd: 'batch',
  cjs: 'javascript',
  command: 'batch',
  console: 'shellscript',
  docker: 'dockerfile',
  gql: 'graphql',
  js: 'javascript',
  kt: 'kotlin',
  kts: 'kotlin',
  md: 'markdown',
  mjs: 'javascript',
  plaintext: 'text',
  ps: 'powershell',
  ps1: 'powershell',
  pwsh: 'powershell',
  py: 'python',
  rb: 'ruby',
  rs: 'rust',
  sh: 'bash',
  shell: 'shellscript',
  terminal: 'shellscript',
  ts: 'typescript',
  txt: 'text',
  yml: 'yaml',
  zsh: 'bash',
};

const loadedLanguages = [
  'javascript',
  'typescript',
  'jsx',
  'tsx',
  'json',
  'jsonc',
  'bash',
  'shellscript',
  'powershell',
  'batch',
  'vue',
  'scss',
  'markdown',
  'yaml',
  'html',
  'css',
  'python',
  'sql',
  'go',
  'rust',
  'java',
  'c',
  'cpp',
  'csharp',
  'ruby',
  'php',
  'swift',
  'kotlin',
  'diff',
  'dockerfile',
  'xml',
  'toml',
  'graphql',
  'text',
] satisfies BundledLanguage[];

const loadedLanguageSet = new Set<string>(loadedLanguages);
const shikiLanguageSet = new Set<string>([...languageNames, ...languageAliasNames]);

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function normalizeShikiLanguage(language: string | undefined): BundledLanguage {
  const raw = String(language || 'text')
    .trim()
    .toLowerCase();
  const normalized = LANGUAGE_ALIASES[raw] ?? raw;
  if (loadedLanguageSet.has(normalized)) return normalized as BundledLanguage;
  if (shikiLanguageSet.has(normalized) && normalized in bundledLanguages) {
    return normalized as BundledLanguage;
  }
  return 'text';
}

export async function getHighlighterInstance(): Promise<Highlighter> {
  if (highlighter) return highlighter;
  if (highlighterPromise) return highlighterPromise;

  highlighterPromise = createHighlighter({
    themes: [lightPlus, darkPlus],
    langs: loadedLanguages,
  }).then((h) => {
    highlighter = h;
    return h;
  });

  return highlighterPromise;
}

export async function highlightCode(
  code: string,
  lang: string,
  theme: 'light' | 'dark' = 'dark',
): Promise<string> {
  const h = await getHighlighterInstance();
  const normalizedLanguage = normalizeShikiLanguage(lang);
  try {
    return h.codeToHtml(code, {
      lang: normalizedLanguage,
      theme: theme === 'dark' ? 'dark-plus' : 'light-plus',
      colorReplacements: {
        '#FFFFFF': 'transparent',
        '#1E1E1E': 'transparent',
      },
    });
  } catch {
    return `<pre class="shiki"><code>${escapeHtml(code)}</code></pre>`;
  }
}
