<template>
  <div>
    <div v-if="!rail">
      <div class="mb-2 flex items-center justify-between rounded px-3 py-1">
        <span class="text-sm font-bold uppercase tracking-normal font-sans text-medium-emphasis dark:text-zinc-400">
          {{ $t('sidebar.projects') }}
        </span>
        <BaseIconButton
          :icon="ChevronDownIcon"
          size="x-small"
          custom-class="opacity-60 hover:opacity-100"
          :class="{ 'rotate-180': isOpen }"
          @click="isOpen = !isOpen"
        />
      </div>

      <v-expand-transition>
        <BaseMenuList v-if="isOpen" tone="nav" bg-color="transparent" list-class="pa-0">
          <BaseMenuListItem
            tone="nav"
            :icon="FolderPlusIcon"
            :label="$t('sidebar.newProject')"
            class="mb-1"
            @click="emit('create')"
          />

          <SidebarProjectItem
            v-for="project in showAllProjects ? projects : projects.slice(0, 4)"
            :key="project.id"
            :project-id="project.id"
            :name="project.name"
            :rail="rail"
            @menu="onMenu"
          />

          <SidebarProjectItem
            v-if="projects.length > 4"
            :project-id="'more-toggle'"
            :name="showAllProjects ? $t('sidebar.less') : $t('sidebar.more')"
            :rail="rail"
            :is-more-toggle="true"
            @toggle-more="showAllProjects = !showAllProjects"
          />
        </BaseMenuList>
      </v-expand-transition>
    </div>

    <BaseRailPanel
      v-else
      :icon="FolderOpenIcon"
      :tooltip="$t('sidebar.projects')"
      :title="$t('sidebar.projects')"
      :width="200"
    >
      <BaseMenuListItem
        v-for="project in projects"
        :key="project.id"
        tone="nav"
        :icon="FolderOpenIcon"
        :label="project.name"
        @click="goToProject(project.id)"
      />

      <template #footer>
        <BaseMenuListItem
          tone="nav"
          :icon="FolderPlusIcon"
          :label="$t('sidebar.newProject')"
          @click="emit('create')"
        />
      </template>
    </BaseRailPanel>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { ChevronDownIcon, FolderPlusIcon, FolderOpenIcon } from 'lucide-vue-next';
import type { MenuItem, SubmenuItem } from '~/types/ui-menu';
import { useProjects } from '~/composables/useProjects';

interface Props {
  rail?: boolean;
}
withDefaults(defineProps<Props>(), {
  rail: false,
});

const emit = defineEmits<{
  (e: 'create'): void;
  (e: 'menu', item: MenuItem | SubmenuItem): void;
}>();

const { projects } = useProjects();
const isOpen = ref(true);
const showAllProjects = ref(false);
const router = useRouter();

function goToProject(projectId: string | number) {
  router.push({ path: `/projects/${projectId}` });
}

function onMenu(item: MenuItem | SubmenuItem) {
  emit('menu', item);
}
</script>
