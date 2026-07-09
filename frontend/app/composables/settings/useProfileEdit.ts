import { computed, ref } from 'vue';
import { useUserStore } from '~/stores/user.store';
import { getInitials, readFileAsDataUrl } from '~/utils/user';

export function useProfileEdit() {
  const userStore = useUserStore();

  const tempName = ref(userStore.name);
  const tempUsername = ref(userStore.nickname);
  const tempEmail = ref(userStore.email);
  const tempPhone = ref(userStore.phone);
  const tempAddress = ref(userStore.address);
  const tempAvatarUrl = ref<string | null>(userStore.avatarUrl || null);
  const fileInput = ref<HTMLInputElement | null>(null);

  const initials = computed(() => getInitials(tempName.value || userStore.name));

  function resetFromStore() {
    tempName.value = userStore.name;
    tempUsername.value = userStore.nickname;
    tempEmail.value = userStore.email;
    tempPhone.value = userStore.phone;
    tempAddress.value = userStore.address;
    tempAvatarUrl.value = userStore.avatarUrl || null;
  }

  function openFilePicker() {
    fileInput.value?.click();
  }

  function onFileChange(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input?.files?.[0];
    if (!file) return;

    readFileAsDataUrl(file)
      .then((url) => {
        tempAvatarUrl.value = url;
      })
      .catch(() => {
        // Ignore read errors for now.
      });

    input.value = '';
  }

  function save() {
    if (tempAvatarUrl.value && tempAvatarUrl.value !== userStore.avatarUrl) {
      userStore.setAvatar(tempAvatarUrl.value);
    }

    userStore.setProfile({
      name: tempName.value.trim() || userStore.name,
      nickname: tempUsername.value.trim() || userStore.nickname,
      email: tempEmail.value.trim() || userStore.email,
      phone: tempPhone.value.trim(),
      address: tempAddress.value.trim(),
      plan: userStore.plan,
    });
  }

  return {
    fileInput,
    initials,
    onFileChange,
    openFilePicker,
    resetFromStore,
    save,
    tempAvatarUrl,
    tempAddress,
    tempEmail,
    tempName,
    tempPhone,
    tempUsername,
  };
}
