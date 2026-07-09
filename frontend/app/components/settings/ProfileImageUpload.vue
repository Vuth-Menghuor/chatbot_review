<template>
  <div class="flex items-center gap-4">
    <div class="relative shrink-0">
      <v-avatar
        size="64"
        color="#e8725a"
        class="overflow-hidden rounded-full ring-1 ring-gray-200 dark:ring-zinc-700"
        theme="dark"
      >
        <img
          v-if="avatarUrl"
          :src="avatarUrl"
          :alt="alt"
          class="h-full w-full object-cover"
        />
        <span v-else class="text-sm font-semibold text-white">{{ initials }}</span>
      </v-avatar>

      <BaseIconButton
        :icon="CameraIcon"
        variant="flat"
        size="x-small"
        custom-class="absolute -right-1 -bottom-1 !h-7 !w-7 !min-w-7 !p-0 !rounded-full border-2 border-white bg-white text-zinc-700 shadow-md ring-1 ring-black/5 hover:bg-zinc-50 hover:text-zinc-950 dark:border-zinc-950 dark:bg-zinc-800 dark:text-zinc-100 dark:ring-white/10 dark:hover:bg-zinc-700"
        icon-class="text-current"
        :aria-label="avatarLabel"
        @click.stop="openFilePicker"
      />
    </div>

    <div class="min-w-0">
      <BaseButton variant="text" size="small" custom-class="px-0" @click="openFilePicker">
        {{ buttonLabel }}
      </BaseButton>
      <p class="settings-item-desc">{{ hint }}</p>
    </div>

    <input
      ref="fileInput"
      type="file"
      accept="image/png,image/jpeg,image/jpg"
      class="hidden"
      @change="$emit('change', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { CameraIcon } from 'lucide-vue-next';

defineProps<{
  alt: string;
  avatarLabel: string;
  avatarUrl: string | null;
  buttonLabel: string;
  hint: string;
  initials: string;
}>();

defineEmits<{
  (event: 'change', value: Event): void;
}>();

const fileInput = ref<HTMLInputElement | null>(null);

function openFilePicker() {
  fileInput.value?.click();
}
</script>
