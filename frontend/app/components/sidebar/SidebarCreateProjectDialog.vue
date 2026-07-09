<template>
  <BaseDialog
    v-model="model"
    :title="$t('project.create.title')"
    width="460px"
    content-class="bg-white dark:bg-zinc-950"
  >
    <p class="mt-0 mb-6 text-sm font-normal text-gray-500 dark:text-zinc-400">
      {{ $t('project.create.description') }}
    </p>

    <BaseInput
      v-model="projectName"
      :label="$t('project.create.nameLabel')"
      :placeholder="$t('project.create.namePlaceholder')"
      class="mb-5"
    />

    <div class="mb-1">
      <label class="mb-2 block text-sm font-medium text-gray-700 dark:text-zinc-300">
        {{ $t('project.create.category') }}
        <span class="ml-1 font-normal text-gray-500 dark:text-zinc-500">
          - {{ $t('common.optional') }}
        </span>
      </label>
      <div class="flex flex-wrap gap-2">
        <v-chip
          v-for="category in PROJECT_CATEGORIES"
          :key="category.id"
          :variant="selectedCategory === category.id ? 'flat' : 'outlined'"
          size="small"
          :class="[
            'category-chip cursor-pointer rounded-lg px-3 py-1 font-medium transition-colors',
            selectedCategory === category.id
              ? 'border border-gray-900 bg-gray-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950'
              : 'border border-gray-300 bg-white text-gray-700 hover:border-gray-400 hover:bg-gray-50 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-900',
          ]"
          @click="handleCategorySelect(category.id)"
        >
          <template #prepend>
            <component :is="categoryIcon(category.id)" class="mr-1.5 h-3.5 w-3.5" />
          </template>
          {{ $t(`project.categories.${category.id}`) }}
        </v-chip>
      </div>
    </div>

    <template #actions>
      <BaseButton variant="outlined" custom-class="text-gray-700" @click="model = false">
        {{ $t('common.cancel') }}
      </BaseButton>
      <BaseButton :disabled="!projectName.trim()" @click="onCreate">
        {{ $t('project.create.submit') }}
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import {
  BriefcaseIcon,
  CircleDollarSignIcon,
  GraduationCapIcon,
  HeartPulseIcon,
  PaletteIcon,
  PlaneIcon,
  SearchIcon,
  UserIcon,
} from 'lucide-vue-next';
import { PROJECT_CATEGORIES, useCreateProject } from '~/utils/projects/create-project';

const model = defineModel<boolean>({ required: true });
const emit = defineEmits<{
  (e: 'create', name: string, category: string): void;
}>();

const { projectName, selectedCategory, handleCategoryChange, handleCreateProject } =
  useCreateProject();

function handleCategorySelect(categoryId: string) {
  handleCategoryChange(categoryId);
}

function onCreate() {
  handleCreateProject(emit);
}

const categoryIcons = {
  work: BriefcaseIcon,
  personal: UserIcon,
  travel: PlaneIcon,
  education: GraduationCapIcon,
  health: HeartPulseIcon,
  finance: CircleDollarSignIcon,
  creative: PaletteIcon,
  research: SearchIcon,
};

function categoryIcon(categoryId: string) {
  return categoryIcons[categoryId as keyof typeof categoryIcons] ?? BriefcaseIcon;
}
</script>

<style scoped>
.category-chip :deep(.v-chip__underlay),
.category-chip :deep(.v-chip__overlay) {
  display: none;
}
</style>
