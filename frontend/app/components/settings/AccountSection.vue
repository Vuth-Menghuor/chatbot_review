<template>
  <section class="space-y-6">
    <SettingsBlock spy-id="account-details" :title="$t('settings.account.detailsTitle')">
      <div class="settings-panel">
        <SettingsFieldRow :label="$t('profile.photo')">
          <ProfileImageUpload
            :alt="tempName"
            :avatar-label="$t('profile.changeAvatar')"
            :avatar-url="tempAvatarUrl"
            :button-label="$t('profile.changePhoto')"
            :hint="$t('profile.photoHint')"
            :initials="initials"
            @change="onFileChange"
          />
        </SettingsFieldRow>

        <SettingsFieldRow :label="$t('profile.displayName')">
          <BaseInput v-model="tempName" :placeholder="$t('profile.displayNamePlaceholder')" />
        </SettingsFieldRow>

        <SettingsFieldRow :label="$t('profile.username')">
          <BaseInput v-model="tempUsername" placeholder="@handle" />
        </SettingsFieldRow>

        <SettingsFieldRow :label="$t('profile.email')">
          <BaseInput v-model="tempEmail" type="email" :placeholder="$t('profile.emailPlaceholder')" />
        </SettingsFieldRow>
      </div>

      <div class="flex flex-col items-end gap-2">
        <p v-if="errorMessage" class="text-right text-sm font-medium text-red-500">{{ errorMessage }}</p>
        <p v-else-if="savedMessage" class="settings-item-desc text-right">{{ savedMessage }}</p>
        <BaseButton :loading="isSaving" :disabled="isSaving" @click="onSave">{{ $t('profile.save') }}</BaseButton>
      </div>
    </SettingsBlock>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useProfileEdit } from '~/composables/settings/useProfileEdit';
import ProfileImageUpload from './ProfileImageUpload.vue';
import SettingsBlock from './SettingsBlock.vue';
import SettingsFieldRow from './SettingsFieldRow.vue';

const { t } = useI18n();

const {
  initials,
  isSaving,
  onFileChange,
  save,
  tempAvatarUrl,
  tempEmail,
  tempName,
  tempUsername,
} = useProfileEdit();

const savedMessage = ref('');
const errorMessage = ref('');

async function onSave() {
  savedMessage.value = '';
  errorMessage.value = '';
  try {
    await save();
    savedMessage.value = t('profile.saveSuccess');
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : t('profile.saveError');
  }
}
</script>
