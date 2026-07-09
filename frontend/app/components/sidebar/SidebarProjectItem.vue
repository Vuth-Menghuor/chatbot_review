<template>
  <BaseMenuListItem
    v-if="!isMoreToggle"
    tone="nav"
    :icon="FolderOpenIcon"
    :label="name"
    :tooltip="name"
    :rail="rail"
    :active="isActive"
    :menu-items="menuItems"
    @click="onProjectClick"
    @menu-select="onMenuSelect"
  />

  <BaseMenuListItem
    v-else
    tone="nav"
    :icon="EllipsisIcon"
    :label="name"
    class="mb-1 cursor-pointer"
    @click="emit('toggle-more', null)"
  />

  <ChatShareDialog v-model="shareOpen" />
  <BaseConfirmDialog
    v-model="renameOpen"
    preset="rename"
    :current-name="name"
    label=" "
    @rename="onRename"
  />
  <BaseConfirmDialog
    v-model="deleteOpen"
    preset="delete"
    :item-name="name"
    item-type="project"
    @confirm="onDelete"
  />
</template>

<script setup lang="ts">
import { useUiStore } from '~/stores/ui.store';
import { useRoute } from 'vue-router';
import { computed, ref } from 'vue';
import { navigateTo } from '#app';
import { FolderOpenIcon, ShareIcon, PencilIcon, Trash2Icon, EllipsisIcon } from 'lucide-vue-next';
import type { MenuEntry, MenuItem, SubmenuItem } from '~/types/ui-menu';
import ChatShareDialog from '~/components/navbar/ChatShareDialog.vue';
import { useProjects } from '~/composables/useProjects';

interface Props {
  projectId: string;
  name: string;
  rail?: boolean;
  isMoreToggle?: boolean;
  showAllProjects?: boolean;
}
const props = withDefaults(defineProps<Props>(), {
  rail: false,
  isMoreToggle: false,
});

const emit = defineEmits<{
  menu: [item: MenuItem | SubmenuItem];
  'toggle-more': [value: null];
}>();

const shareOpen = ref(false);
const renameOpen = ref(false);
const deleteOpen = ref(false);

const uiStore = useUiStore();
const { renameProject, deleteProject } = useProjects();
const { t } = useI18n();
const route = useRoute();

const isActive = computed(() => route.path.includes(`/projects/${props.projectId}`));

const menuItems = computed<MenuEntry[]>(() => [
  {
    label: t('common.share'),
    icon: ShareIcon,
    onClick: () => {
      shareOpen.value = true;
    },
  },
  {
    label: t('common.rename'),
    icon: PencilIcon,
    onClick: () => {
      renameOpen.value = true;
    },
  },
  { type: 'divider' },
  {
    label: t('common.delete'),
    icon: Trash2Icon,
    danger: true,
    onClick: () => {
      deleteOpen.value = true;
    },
  },
]);

function onProjectClick() {
  uiStore.closeMobileSidebar();
  navigateTo(`/projects/${props.projectId}`);
}

function onMenuSelect(item: MenuItem | SubmenuItem) {
  emit('menu', item);
}

function onRename(newName: string) {
  renameProject(props.projectId, newName);
  renameOpen.value = false;
}

function onDelete() {
  deleteProject(props.projectId);
  deleteOpen.value = false;
}
</script>
