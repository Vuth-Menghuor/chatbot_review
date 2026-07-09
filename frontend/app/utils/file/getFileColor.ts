export function getFileColor(fileName: string): string {
  const ext = fileName.split('.').pop()?.toLowerCase();

  switch (ext) {
    case 'pdf':
      return 'bg-red-500';
    case 'doc':
    case 'docx':
      return 'bg-blue-600';
    case 'xls':
    case 'xlsx':
      return 'bg-emerald-600';
    case 'csv':
      return 'bg-teal-500';
    case 'txt':
      return 'bg-zinc-500';
    default:
      return 'bg-orange-500';
  }
}
