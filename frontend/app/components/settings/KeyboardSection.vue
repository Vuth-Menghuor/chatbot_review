<template>
  <div class="space-y-4">
    <SettingsShortcutGroup
      v-for="group in groups"
      :key="group.id"
      :spy-id="`keyboard-${group.id}`"
      :title-key="group.titleKey"
      :items="group.items"
    />
  </div>
</template>

<script setup lang="ts">
import { useKeyboardShortcutCatalog } from '~/composables/keyboard/useKeyboardShortcutCatalog';

const { groups } = useKeyboardShortcutCatalog();
</script>
