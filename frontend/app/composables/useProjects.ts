import { useProjectStore } from '~/stores/project.store';
import { storeToRefs } from 'pinia';

export const useProjects = () => {
  const projectStore = useProjectStore();
  const { projects } = storeToRefs(projectStore);

  const createProject = (name: string, description?: string) => {
    return projectStore.addProject(name, description);
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
