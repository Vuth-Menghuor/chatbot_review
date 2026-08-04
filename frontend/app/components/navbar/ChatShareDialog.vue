<template>
  <BaseDialog
    v-model="model"
    :title="dialogTitle"
    content-class="bg-white dark:bg-zinc-950"
    :on-close="onClose"
  >
    <p class="text-base mb-5" :class="linkCreated ? 'text-gray-500 dark:text-zinc-400 -mt-1' : ''">
      {{ helperText }}
    </p>

    <div
      :class="[
        'w-full overflow-hidden rounded-xl border border-gray-200 bg-gray-50 dark:border-zinc-700 dark:bg-zinc-900/50',
        linkCreated ? 'mb-5' : 'mb-4',
      ]"
    >
      <BaseMenuList tone="menu" plain full-width list-class="pa-0 w-full">
        <BaseMenuListItem
          v-for="option in shareOptions"
          :key="option.id"
          appearance="select"
          :icon="option.icon"
          :label="option.title"
          :description="option.description"
          :active="shareType === option.id"
          :disabled="linkCreated"
          @click="onSelectOption(option.id)"
        >
          <template #append>
            <CheckIcon
              v-if="shareType === option.id"
              class="h-5.5 w-5.5 shrink-0 text-blue-600 dark:text-blue-400"
            />
          </template>
        </BaseMenuListItem>
      </BaseMenuList>
    </div>

    <template v-if="!linkCreated">
      <p class="text-[13px] leading-relaxed text-gray-600 dark:text-zinc-500">
        Don't share personal information or third-party content without permission, and see our
        <NuxtLink to="/policy">Usage Policy</NuxtLink>.
      </p>
    </template>

    <template v-else>
      <BaseCopy v-if="shareType === 'public'" variant="box" :value="shareLink" />
      <div
        v-else
        class="rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-600 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
      >
        Only you can access this chat.
      </div>
    </template>

    <p v-if="errorMessage" class="mt-3 text-sm text-red-600 dark:text-red-400">
      {{ errorMessage }}
    </p>

    <template #actions>
      <template v-if="!linkCreated">
        <BaseButton variant="text" custom-class="text-gray-500" @click="model = false">
          Cancel
        </BaseButton>
        <BaseButton elevation="0" :loading="isSaving" @click="updateSharing">
          {{ primaryActionLabel }}
        </BaseButton>
      </template>
      <template v-else>
        <BaseButton variant="text" custom-class="text-gray-500" @click="model = false">
          Close
        </BaseButton>
      </template>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { CheckIcon } from 'lucide-vue-next';
import { useNavbarChatShareDialog } from '~/composables/navbar/useChatShareDialog';
import type { NavbarShareType } from '~/types/ui-menu';
const model = defineModel<boolean>({ required: true });

const props = defineProps<{
  chatId?: string;
}>();

const {
  shareType,
  linkCreated,
  isSaving,
  errorMessage,
  dialogTitle,
  helperText,
  primaryActionLabel,
  shareOptions,
  shareLink,
  updateSharing,
  onClose,
} = useNavbarChatShareDialog({ chatId: computed(() => props.chatId) });

function onSelectOption(id: NavbarShareType) {
  if (linkCreated.value) return;
  shareType.value = id;
}
</script>
