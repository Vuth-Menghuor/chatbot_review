import { defineStore } from 'pinia';
import { ref, watch } from 'vue';
import { readJson, removeKey, storageKeys, writeJson } from '~/utils/storage';
import type { Project } from '~/types/message';

export const useProjectStore = defineStore('project', () => {
  const projects = ref<Project[]>([]);
  const isLoaded = ref(false);

  if (import.meta.client) {
    projects.value = readJson<Project[]>(storageKeys.projectList, []);
    isLoaded.value = true;
  }

  // Persist changes
  watch(
    projects,
    (val) => {
      if (isLoaded.value) {
        writeJson(storageKeys.projectList, val);
      }
    },
    { deep: true },
  );

  function addProject(name: string, description?: string, backendId?: string) {
    const slug = name.toLowerCase().replace(/\s+/g, '-');
    // Generate a 32-character random hex-like hash
    const hash = Array.from({ length: 4 }, () => Math.random().toString(16).substring(2, 10)).join(
      '',
    );
    const id = `g-p-${hash}-${slug}`;
    const newProject: Project = {
      id,
      backendId,
      name,
      description,
      createdAt: new Date().toISOString(),
    };
    projects.value.unshift(newProject);
    return newProject;
  }

  function setBackendProjectId(localProjectId: string, backendId: string) {
    const project = projects.value.find((p) => p.id === localProjectId);
    if (!project) return;
    project.backendId = backendId;
    if (isLoaded.value) {
      writeJson(storageKeys.projectList, projects.value);
    }
  }

  function deleteProject(id: string) {
    projects.value = projects.value.filter((p) => p.id !== id);
  }

  function renameProject(id: string, newName: string) {
    const project = projects.value.find((p) => p.id === id);
    if (project) {
      project.name = newName;
    }
  }

  function clearAll() {
    projects.value = [];
    removeKey(storageKeys.projectList);
  }

  return {
    projects,
    addProject,
    setBackendProjectId,
    deleteProject,
    renameProject,
    clearAll,
  };
});
