import type { PDFPageProxy } from 'pdfjs-dist/types/src/display/api';

interface PdfOcrOptions {
  maxTextPages?: number;
  maxImagePages?: number;
  imageScale?: number;
  imageType?: 'image/png' | 'image/jpeg';
  imageQuality?: number;
}

export interface PdfOcrPreparation {
  text: string;
  imageDataUrls: string[];
  pageCount: number;
  textPageCount: number;
  renderedPageCount: number;
}

const DEFAULT_MAX_TEXT_PAGES = 20;
const DEFAULT_MAX_IMAGE_PAGES = 3;
const DEFAULT_IMAGE_SCALE = 2;

let workerConfigured = false;

async function loadPdfJs() {
  const pdfjs = await import('pdfjs-dist');
  if (!workerConfigured) {
    pdfjs.GlobalWorkerOptions.workerSrc = new URL(
      'pdfjs-dist/build/pdf.worker.mjs',
      import.meta.url,
    ).toString();
    workerConfigured = true;
  }
  return pdfjs;
}

function normalizeText(text: string) {
  return text
    .replaceAll(String.fromCharCode(0), '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function isTextItem(item: unknown): item is { str: string } {
  return Boolean(
    item && typeof item === 'object' && typeof (item as { str?: unknown }).str === 'string',
  );
}

async function extractTextFromPage(page: PDFPageProxy) {
  const content = await page.getTextContent();
  const items: unknown[] = Array.isArray(content?.items) ? content.items : [];
  return items
    .filter(isTextItem)
    .map((item) => item.str)
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim();
}

async function renderPageToImageDataUrl(
  page: PDFPageProxy,
  options: Required<Pick<PdfOcrOptions, 'imageScale' | 'imageType' | 'imageQuality'>>,
) {
  const viewport = page.getViewport({ scale: options.imageScale });
  const canvas = document.createElement('canvas');
  canvas.width = Math.ceil(viewport.width);
  canvas.height = Math.ceil(viewport.height);

  await page.render({ canvas, viewport }).promise;

  const dataUrl =
    options.imageType === 'image/jpeg'
      ? canvas.toDataURL(options.imageType, options.imageQuality)
      : canvas.toDataURL(options.imageType);

  canvas.width = 0;
  canvas.height = 0;
  return dataUrl;
}

export async function preparePdfForOcr(
  file: File,
  options: PdfOcrOptions = {},
): Promise<PdfOcrPreparation> {
  const pdfjs = await loadPdfJs();
  const data = new Uint8Array(await file.arrayBuffer());
  const loadingTask = pdfjs.getDocument({ data });
  const pdf = await loadingTask.promise;

  const maxTextPages = Math.min(options.maxTextPages ?? DEFAULT_MAX_TEXT_PAGES, pdf.numPages);
  const textParts: string[] = [];

  for (let pageNumber = 1; pageNumber <= maxTextPages; pageNumber++) {
    const page = await pdf.getPage(pageNumber);
    const pageText = await extractTextFromPage(page);
    if (pageText) {
      textParts.push(`Page ${pageNumber}\n${pageText}`);
    }
    page.cleanup?.();
  }

  const text = normalizeText(textParts.join('\n\n'));
  if (text) {
    await loadingTask.destroy?.();
    return {
      text,
      imageDataUrls: [],
      pageCount: pdf.numPages,
      textPageCount: textParts.length,
      renderedPageCount: 0,
    };
  }

  const maxImagePages = Math.min(options.maxImagePages ?? DEFAULT_MAX_IMAGE_PAGES, pdf.numPages);
  const imageDataUrls: string[] = [];
  const renderOptions = {
    imageScale: options.imageScale ?? DEFAULT_IMAGE_SCALE,
    imageType: options.imageType ?? 'image/png',
    imageQuality: options.imageQuality ?? 0.92,
  } satisfies Required<Pick<PdfOcrOptions, 'imageScale' | 'imageType' | 'imageQuality'>>;

  for (let pageNumber = 1; pageNumber <= maxImagePages; pageNumber++) {
    const page = await pdf.getPage(pageNumber);
    imageDataUrls.push(await renderPageToImageDataUrl(page, renderOptions));
    page.cleanup?.();
  }

  await loadingTask.destroy?.();
  return {
    text: '',
    imageDataUrls,
    pageCount: pdf.numPages,
    textPageCount: 0,
    renderedPageCount: imageDataUrls.length,
  };
}
