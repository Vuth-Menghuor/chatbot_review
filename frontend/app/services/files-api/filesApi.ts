import { buildChatApiUrl, ChatApiRequestError } from '~/services/chat-api/chatApiHttp';
import { tryRefreshSession } from '~/services/auth-api/authApi';

export interface FileUploadResult {
  file_id: string;
  object_key: string;
  bucket: string;
  status: string;
  url: string | null;
}

function parseUploadError(body: string, status: number): string {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    if (typeof parsed.detail === 'string' && parsed.detail.trim()) return parsed.detail;
  } catch {
    // fall through
  }
  if (status === 401) return 'Authentication required';
  if (status === 413) return 'Image is too large';
  if (status === 400) return 'Invalid image file';
  return 'Image upload failed';
}

async function uploadOnce(baseUrl: string, accessToken: string, file: File): Promise<FileUploadResult> {
  const formData = new FormData();
  formData.append('file', file, file.name);

  const response = await fetch(buildChatApiUrl(baseUrl, '/api/v1/files/upload-image'), {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: formData,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new ChatApiRequestError(parseUploadError(body, response.status), response.status, body);
  }

  return (await response.json()) as FileUploadResult;
}

/** Upload image via multipart/form-data with one 401 refresh retry. */
export async function uploadImageFile(
  baseUrl: string,
  accessToken: string,
  file: File,
  onAccessTokenRefreshed?: (accessToken: string) => void,
): Promise<FileUploadResult> {
  try {
    return await uploadOnce(baseUrl, accessToken, file);
  } catch (err) {
    if (!(err instanceof ChatApiRequestError) || err.status !== 401) throw err;

    const refreshed = await tryRefreshSession(baseUrl);
    if (!refreshed?.access_token) throw err;
    onAccessTokenRefreshed?.(refreshed.access_token);
    return uploadOnce(baseUrl, refreshed.access_token, file);
  }
}
