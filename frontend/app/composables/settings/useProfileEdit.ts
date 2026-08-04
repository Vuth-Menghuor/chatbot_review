import { computed, ref, watch } from 'vue';
import { useAuthStore } from '~/stores/auth.store';
import { useUserStore } from '~/stores/user.store';
import { getInitials, readFileAsDataUrl } from '~/utils/user';

export function useProfileEdit() {
  const userStore = useUserStore();
  const authStore = useAuthStore();

  const tempName = ref(userStore.name);
  const tempUsername = ref(userStore.nickname);
  const tempEmail = ref(userStore.email);
  const tempAvatarUrl = ref<string | null>(userStore.avatarUrl || null);
  const fileInput = ref<HTMLInputElement | null>(null);
  const isDirty = ref(false);
  const isSaving = ref(false);
  let isSyncingFromStore = false;

  const initials = computed(() => getInitials(tempName.value || userStore.name));

  function resetFromStore() {
    isSyncingFromStore = true;
    tempName.value = userStore.name;
    tempUsername.value = userStore.nickname;
    tempEmail.value = userStore.email;
    tempAvatarUrl.value = userStore.avatarUrl || null;
    isSyncingFromStore = false;
  }

  function openFilePicker() {
    fileInput.value?.click();
  }

  function onFileChange(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input?.files?.[0];
    if (!file) return;
    isDirty.value = true;

    readFileAsDataUrl(file)
      .then((url) => {
        tempAvatarUrl.value = url;
      })
      .catch(() => {
        // Ignore read errors for now.
      });

    input.value = '';
  }

  async function save() {
    isSaving.value = true;

    try {
      await authStore.updateMe({
        full_name: tempName.value.trim() || userStore.name,
        nickname: tempUsername.value.trim() || null,
        email: tempEmail.value.trim() || userStore.email,
        avatar_url: tempAvatarUrl.value || null,
      });
      isDirty.value = false;
      resetFromStore();
    } finally {
      isSaving.value = false;
    }
  }

  watch(
    () => [
      userStore.name,
      userStore.nickname,
      userStore.email,
      userStore.avatarUrl,
    ],
    () => {
      if (!isDirty.value) resetFromStore();
    },
  );

  watch([tempName, tempUsername, tempEmail, tempAvatarUrl], () => {
    if (isSyncingFromStore) return;
    isDirty.value = true;
  });

  return {
    fileInput,
    initials,
    isSaving,
    onFileChange,
    openFilePicker,
    resetFromStore,
    save,
    tempAvatarUrl,
    tempEmail,
    tempName,
    tempUsername,
  };
}
