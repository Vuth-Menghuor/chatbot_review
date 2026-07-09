<template>
  <section class="space-y-6">
    <AppearanceSection />
    <LanguageSection
      :languages="languages"
      :active-language="activeLanguage"
      @update:active-language="(v) => (activeLanguage = v)"
    />
    <ChatSection />
    <UiSection />
  </section>
</template>

<script setup lang="ts">
import AppearanceSection from './AppearanceSection.vue';
import ChatSection from './ChatSection.vue';
import LanguageSection from './LanguageSection.vue';
import UiSection from './UiSection.vue';
import type { AppLanguage, AppLanguageOption } from '~/composables/useLanguages';

defineProps<{
  languages: readonly AppLanguageOption[];
}>();

const activeLanguage = defineModel<AppLanguage>('activeLanguage', { required: true });
</script>
