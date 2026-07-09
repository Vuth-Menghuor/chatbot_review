const DEFAULT_ALLOWED_TYPES = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
const DEFAULT_MAX_MB = 5;

export interface ImageUploadLimits {
  allowedTypes: string[];
  maxBytes: number;
}

export function getImageUploadLimits(
  allowedTypes?: string[] | string,
  maxImageSizeMb?: number | string,
): ImageUploadLimits {
  let types = DEFAULT_ALLOWED_TYPES;
  if (Array.isArray(allowedTypes) && allowedTypes.length) {
    types = allowedTypes.map((item) => item.toLowerCase());
  } else if (typeof allowedTypes === 'string' && allowedTypes.trim()) {
    types = allowedTypes.split(',').map((item) => item.trim().toLowerCase()).filter(Boolean);
  }

  const mb = Number(maxImageSizeMb);
  const maxBytes = (Number.isFinite(mb) && mb > 0 ? mb : DEFAULT_MAX_MB) * 1024 * 1024;
  return { allowedTypes: types, maxBytes };
}

export function imageAcceptAttribute(limits?: ImageUploadLimits): string {
  const types = limits?.allowedTypes ?? DEFAULT_ALLOWED_TYPES;
  const extensions = new Set<string>();
  for (const type of types) {
    if (type.includes('jpeg') || type.includes('jpg')) {
      extensions.add('.jpg');
      extensions.add('.jpeg');
    } else if (type.includes('png')) extensions.add('.png');
    else if (type.includes('webp')) extensions.add('.webp');
  }
  return [...types, ...extensions].join(',');
}

export function validateImageFile(file: File, limits: ImageUploadLimits): string | null {
  const contentType = (file.type || '').split(';', 1)[0].trim().toLowerCase();
  const extension = file.name.includes('.') ? file.name.slice(file.name.lastIndexOf('.')).toLowerCase() : '';
  const allowedExtensions = new Set(['.jpg', '.jpeg', '.png', '.webp']);

  if (extension && !allowedExtensions.has(extension)) {
    return 'Only JPG, PNG, and WebP images are allowed.';
  }
  if (contentType && !limits.allowedTypes.includes(contentType)) {
    return 'Invalid image type. Allowed: JPG, PNG, WebP.';
  }
  if (file.size <= 0) return 'Empty file is not allowed.';
  if (file.size > limits.maxBytes) {
    const maxMb = Math.round(limits.maxBytes / (1024 * 1024));
    return `Image is too large. Maximum size is ${maxMb} MB.`;
  }
  return null;
}
