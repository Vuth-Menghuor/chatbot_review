/**
 * Build placeholder image URLs via [Lorem Picsum](https://picsum.photos/).
 * Used for local/mock image generation testing only.
 */

export interface PicsumImageUrlOptions {
  seed?: string;
  width?: number;
  height?: number;
  grayscale?: boolean;
  blur?: number;
}

export function promptToPicsumSeed(prompt: string): string {
  const trimmed = prompt.trim().toLowerCase();
  if (!trimmed) return 'gdce-mock-image';
  return trimmed
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48);
}

/** Same seed → same image (see picsum `/seed/{seed}` docs). */
export function buildPicsumImageUrl(options: PicsumImageUrlOptions = {}): string {
  const seed = options.seed ?? 'gdce-mock-image';
  const width = options.width ?? 768;
  const height = options.height ?? 512;
  const base = `https://picsum.photos/seed/${encodeURIComponent(seed)}/${width}/${height}`;
  const params = new URLSearchParams();
  if (options.grayscale) params.set('grayscale', '');
  if (typeof options.blur === 'number' && options.blur > 0) {
    params.set('blur', String(Math.min(10, Math.max(1, options.blur))));
  }
  const query = params.toString();
  return query ? `${base}?${query}` : base;
}

export function buildPicsumImageUrlFromPrompt(
  prompt: string,
  options: Omit<PicsumImageUrlOptions, 'seed'> = {},
): string {
  return buildPicsumImageUrl({ ...options, seed: promptToPicsumSeed(prompt) });
}
