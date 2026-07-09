import type { FileTypeIconPreset } from '~/types/message';

/**
 * Maps a file extension (uppercase, no dot) to a colored tile + Lucide icon,
 * shared by `FileTypeIconBadge` and any caller that needs the same mapping.
 */
export function getFileTypeIconPreset(extension: string): FileTypeIconPreset {
  const ext = (extension || 'FILE').toUpperCase();

  if (ext === 'PDF') return { boxClass: 'bg-red-500', icon: 'lucide-file-text' };
  if (['DOC', 'DOCX', 'RTF', 'ODT'].includes(ext))
    return { boxClass: 'bg-blue-600', icon: 'lucide-file-text' };
  if (['XLS', 'XLSX', 'CSV', 'ODS'].includes(ext))
    return { boxClass: 'bg-emerald-600', icon: 'lucide-file-spreadsheet' };
  if (['PPT', 'PPTX', 'KEY'].includes(ext))
    return { boxClass: 'bg-orange-500', icon: 'lucide-file-text' };
  if (['PNG', 'JPG', 'JPEG', 'GIF', 'WEBP', 'SVG', 'BMP', 'ICO'].includes(ext))
    return { boxClass: 'bg-violet-500', icon: 'lucide-image' };
  if (['ZIP', 'RAR', '7Z', 'TAR', 'GZ', 'BZ2'].includes(ext))
    return { boxClass: 'bg-amber-500', icon: 'lucide-archive' };
  if (['TXT', 'MD', 'LOG'].includes(ext))
    return { boxClass: 'bg-slate-500', icon: 'lucide-file-text' };
  if (
    [
      'JS',
      'TS',
      'TSX',
      'JSX',
      'VUE',
      'JSON',
      'HTML',
      'CSS',
      'SCSS',
      'PY',
      'JAVA',
      'GO',
      'RS',
    ].includes(ext)
  )
    return { boxClass: 'bg-sky-600', icon: 'lucide-file-code' };
  if (['MP4', 'WEBM', 'MOV', 'MKV', 'AVI'].includes(ext))
    return { boxClass: 'bg-pink-600', icon: 'lucide-file-video' };
  if (['MP3', 'WAV', 'FLAC', 'M4A', 'OGG'].includes(ext))
    return { boxClass: 'bg-fuchsia-600', icon: 'lucide-file-audio' };

  return { boxClass: 'bg-gray-400 dark:bg-zinc-600', icon: 'lucide-file' };
}
