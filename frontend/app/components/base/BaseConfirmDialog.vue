<template>
  <BaseDialog v-model="model" :title="resolvedTitle" :width="resolvedWidth">
    <template v-if="preset === 'logout'">
      <p class="mb-6 text-sm text-medium-emphasis">
        <slot>{{ message ?? $t('logout.message') }}</slot>
      </p>
    </template>

    <template v-else-if="preset === 'delete'">
      <div class="flex items-start gap-4">
        <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-error/12 text-error">
          <v-icon icon="lucide-trash-2" size="20" />
        </div>
        <div class="min-w-0">
          <p class="text-sm font-medium text-high-emphasis">
            {{ $t('dialogs.delete.message', { itemName: itemNameText }) }}
          </p>
          <p class="mt-2 text-sm text-medium-emphasis">
            {{ $t('dialogs.delete.cannotUndo') }}
          </p>
        </div>
      </div>
    </template>

    <template v-else-if="preset === 'rename'">
      <BaseInput
        v-model="localName"
        :label="resolvedRenameLabel"
        autofocus
        @keyup.enter="onRenameConfirm"
      />
    </template>

    <p v-else-if="message" class="mb-6 text-sm text-medium-emphasis">
      <slot>{{ message }}</slot>
    </p>
    <slot v-else />

    <template #actions>
      <BaseButton variant="text" custom-class="text-gray-500" @click="model = false">
        {{ resolvedCancelLabel }}
      </BaseButton>
      <BaseButton
        :disabled="confirmDisabled"
        :loading="loading"
        :custom-class="isDanger ? '!bg-red-500 !text-white' : ''"
        elevation="0"
        @click="onConfirmClick"
      >
        {{ resolvedConfirmLabel }}
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
export type BaseConfirmPreset = 'logout' | 'rename' | 'delete';

interface Props {
  /** Built-in body + i18n for logout, rename, or delete. Omit for custom slot content. */
  preset?: BaseConfirmPreset;
  title?: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  disabled?: boolean;
  loading?: boolean;
  danger?: boolean;
  width?: number;
  /** Rename preset */
  currentName?: string;
  label?: string;
  /** Delete preset */
  itemName?: string;
  itemType?: string;
}

const props = withDefaults(defineProps<Props>(), {
  confirmLabel: undefined,
  cancelLabel: undefined,
  width: undefined,
  disabled: false,
  loading: false,
  danger: false,
  currentName: '',
});

const model = defineModel<boolean>({ required: true });

const emit = defineEmits<{
  confirm: [];
  rename: [name: string];
}>();

const { t } = useI18n();
const localName = ref(props.currentName);

const isDanger = computed(
  () => props.danger || props.preset === 'logout' || props.preset === 'delete',
);

const resolvedWidth = computed(() => {
  if (props.width !== undefined) return props.width;
  if (props.preset === 'logout' || props.preset === 'rename') return 420;
  if (props.preset === 'delete') return 400;
  return 480;
});

const resolvedTitle = computed(() => {
  if (props.title) return props.title;
  if (props.preset === 'logout') return t('logout.title');
  if (props.preset === 'rename') return t('dialogs.rename.title');
  if (props.preset === 'delete') {
    return t('dialogs.delete.title', { itemType: itemTypeText.value });
  }
  return undefined;
});

const resolvedConfirmLabel = computed(() => {
  if (props.confirmLabel) return props.confirmLabel;
  if (props.preset === 'logout') return t('logout.confirm');
  if (props.preset === 'rename') return t('common.rename');
  if (props.preset === 'delete') return t('common.delete');
  return 'Confirm';
});

const resolvedCancelLabel = computed(() => props.cancelLabel ?? t('common.cancel'));

const resolvedRenameLabel = computed(() => props.label ?? t('dialogs.rename.newName'));

const itemNameText = computed(() => props.itemName || t('dialogs.delete.defaultItem'));
const itemTypeText = computed(() => props.itemType || t('dialogs.delete.defaultType'));

const confirmDisabled = computed(() => {
  if (props.preset === 'rename') return !localName.value.trim();
  return props.disabled;
});

watch(
  () => props.currentName,
  (val) => {
    localName.value = val;
  },
);

watch(
  () => model.value,
  (open) => {
    if (open && props.preset === 'rename') {
      localName.value = props.currentName;
    }
  },
);

function onRenameConfirm() {
  if (!localName.value.trim()) return;
  emit('rename', localName.value.trim());
}

function onConfirmClick() {
  if (props.preset === 'rename') {
    onRenameConfirm();
    return;
  }
  emit('confirm');
}
</script>
