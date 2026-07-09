import { ref } from 'vue';
import type { ProjectCategory } from '~/types/message';

export const PROJECT_CATEGORIES: ProjectCategory[] = [
  { id: 'work', name: 'Work', emoji: '💼' },
  { id: 'personal', name: 'Personal', emoji: '🏠' },
  { id: 'travel', name: 'Travel', emoji: '✈️' },
  { id: 'education', name: 'Education', emoji: '📚' },
  { id: 'health', name: 'Health', emoji: '🏥' },
  { id: 'finance', name: 'Finance', emoji: '💰' },
  { id: 'creative', name: 'Creative', emoji: '🎨' },
  { id: 'research', name: 'Research', emoji: '🔬' },
];

export function useCreateProject() {
  // const { createProject } = useProjects();

  const projectName = ref('');
  const selectedCategory = ref('');
  const { t } = useI18n();

  function categoryName(categoryId: string) {
    return t(`project.categories.${categoryId}`);
  }

  function handleCategoryChange(categoryId: string) {
    const previousCategory = selectedCategory.value;
    selectedCategory.value = categoryId;

    // Auto-fill or update project name based on selected category
    const category = PROJECT_CATEGORIES.find((cat) => cat.id === categoryId);
    if (category) {
      const suggestedName = `${categoryName(category.id)} ${t('project.defaultTitle')}`;
      // Only auto-fill if field is empty OR if it contains a previously auto-generated name
      const previousSuggestedName = previousCategory
        ? `${categoryName(previousCategory)} ${t('project.defaultTitle')}`
        : '';

      if (!projectName.value.trim() || projectName.value.trim() === previousSuggestedName) {
        projectName.value = suggestedName;
      }
    }
  }

  function handleCreateProject(emit: (event: 'create', name: string, category: string) => void) {
    if (!projectName.value.trim()) return;

    const category = selectedCategory.value || '';
    // Remove the createProject call - let the parent component handle creation
    // createProject(projectName.value.trim(), category);

    emit('create', projectName.value.trim(), category);

    // Reset form
    projectName.value = '';
    selectedCategory.value = '';
  }

  return {
    projectName,
    selectedCategory,
    handleCategoryChange,
    handleCreateProject,
  };
}
