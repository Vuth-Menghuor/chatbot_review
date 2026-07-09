<template>
  <BaseDialog
    v-model="model"
    :title="linkCreated ? 'Chat shared' : 'Share chat'"
    content-class="bg-white dark:bg-zinc-950"
    :on-close="onClose"
  >
    <p class="text-base mb-5" :class="linkCreated ? 'text-gray-500 dark:text-zinc-400 -mt-1' : ''">
      {{
        linkCreated
          ? "Future messages aren't included."
          : 'Only messages up to this point will be shared.'
      }}
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
      <BaseCopy variant="box" :value="shareLink" />
    </template>

    <template #actions>
      <template v-if="!linkCreated">
        <BaseButton variant="text" custom-class="text-gray-500" @click="model = false">
          Cancel
        </BaseButton>
        <BaseButton elevation="0" @click="createLink">Create share link</BaseButton>
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
import { CheckIcon } from 'lucide-vue-next';
import { useNavbarChatShareDialog } from '~/composables/navbar/useChatShareDialog';
import type { NavbarShareType } from '~/types/ui-menu';
const model = defineModel<boolean>({ required: true });

const { shareType, linkCreated, shareOptions, shareLink, createLink, onClose } =
  useNavbarChatShareDialog();

function onSelectOption(id: NavbarShareType) {
  if (linkCreated.value) return;
  shareType.value = id;
}
</script>
