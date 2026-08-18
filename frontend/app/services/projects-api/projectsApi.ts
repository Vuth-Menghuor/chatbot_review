import { authFetchAuthed } from '~/services/auth-api/authApi';

export interface ProjectApiPayload {
  name: string;
  description?: string;
}

export interface ProjectApiResponse {
  id: string;
  name: string;
  description?: string | null;
}

export async function createProjectRequest(
  baseUrl: string,
  accessToken: string,
  payload: ProjectApiPayload,
) {
  return authFetchAuthed<ProjectApiResponse>(baseUrl, '/api/v1/projects', accessToken, {
    body: {
      name: payload.name,
      description: payload.description || undefined,
    },
  });
}
