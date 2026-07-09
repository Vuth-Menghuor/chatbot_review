<template>
  <div class="px-4 py-1">
    <span
      class="text-base font-semibold text-gray-900 dark:text-zinc-100 truncate max-w-[300px] block"
    >
      {{ displayTitle }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { useNavbarChatTitle } from '~/composables/navbar/useChatTitle';

const { displayTitle } = useNavbarChatTitle();
</script>
