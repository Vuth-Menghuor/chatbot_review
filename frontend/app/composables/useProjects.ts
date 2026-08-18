import { useProjectStore } from '~/stores/project.store';
import { storeToRefs } from 'pinia';
import { useAuthStore } from '~/stores/auth.store';
import { ChatApiRequestError } from '~/services/chat-api';
import { createProjectRequest } from '~/services/projects-api';
import { backendUuidOrNull } from '~/utils/id/backendIdentity';

export const useProjects = () => {
  const projectStore = useProjectStore();
  const authStore = useAuthStore();
  const { projects } = storeToRefs(projectStore);

  function apiBaseUrl(): string {
    const runtimeConfig = useRuntimeConfig();
    return String(runtimeConfig.public?.gdceApiBaseUrl ?? 'http://localhost:8000').replace(/\/+$/, '');
  }

  const createProject = async (name: string, description?: string) => {
    const token = await authStore.getValidAccessToken();
    if (!token) {
      throw new Error('Please sign in before creating a project workspace.');
    }

    const localProject = projectStore.addProject(name, description);
    try {
      const result = await createProjectRequest(apiBaseUrl(), token, { name, description });
      authStore.accessToken = result.accessToken;
      authStore.refreshToken = result.refreshToken;
      const backendProjectId = backendUuidOrNull(result.data.id);
      if (!backendProjectId) {
        throw new Error('Project creation did not return a valid backend project ID.');
      }
      projectStore.setBackendProjectId(localProject.id, backendProjectId);
    } catch (error) {
      projectStore.deleteProject(localProject.id);
      if (import.meta.dev && error instanceof ChatApiRequestError) {
        console.error('[GDCE project creation failed]', {
          status: error.status,
          body: error.body,
          message: error.message,
        });
      }
      throw error;
    }

    return localProject;
  };

  const deleteProject = (id: string) => {
    projectStore.deleteProject(id);
  };

  const renameProject = (id: string, newName: string) => {
    projectStore.renameProject(id, newName);
  };

  return {
    projects,
    createProject,
    deleteProject,
    renameProject,
  };
};
